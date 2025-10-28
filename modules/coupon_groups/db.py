from datetime import datetime

from sqlalchemy import case, delete, func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from logger import logger

from .models import CouponGroup, CouponGroupItem, CouponGroupUsage



async def create_coupon_group(session: AsyncSession, name: str) -> CouponGroup | None:
    try:
        exists = await session.scalar(select(CouponGroup.id).where(CouponGroup.name == name))
        if exists:
            logger.warning(f"[CouponGroups] ⚠️ Группа с названием {name} уже существует")
            return None
        group = CouponGroup(name=name)
        session.add(group)
        await session.commit()
        await session.refresh(group)
        logger.info(f"[CouponGroups] ✅ Группа {name} успешно создана (ID: {group.id})")
        return group
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[CouponGroups] ❌ Ошибка при создании группы {name}: {e}")
        return None


async def get_coupon_group_by_id(session: AsyncSession, group_id: int) -> CouponGroup | None:
    stmt = select(CouponGroup).where(CouponGroup.id == group_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_coupon_group_by_name(session: AsyncSession, name: str) -> CouponGroup | None:
    stmt = select(CouponGroup).where(CouponGroup.name == name)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_all_coupon_groups(session: AsyncSession, page: int = 1, per_page: int = 10) -> dict:
    try:
        offset = (page - 1) * per_page
        stmt = select(CouponGroup).order_by(CouponGroup.id.desc()).offset(offset).limit(per_page)
        result = await session.execute(stmt)
        groups = result.scalars().all()

        count_stmt = select(func.count()).select_from(CouponGroup)
        total = await session.scalar(count_stmt)
        pages = -(-total // per_page) if total > 0 else 1

        return {
            "groups": [g.to_dict() for g in groups],
            "total": total,
            "pages": pages,
            "current_page": page,
        }
    except SQLAlchemyError as e:
        logger.error(f"[CouponGroups] ❌ Ошибка при получении списка групп: {e}")
        return {"groups": [], "total": 0, "pages": 1, "current_page": 1}


async def delete_coupon_group(session: AsyncSession, group_id: int) -> bool:
    try:
        result = await session.execute(select(CouponGroup).where(CouponGroup.id == group_id))
        group = result.scalar_one_or_none()
        if not group:
            logger.info(f"[CouponGroups] ❌ Группа с ID {group_id} не найдена")
            return False

        await session.delete(group)
        await session.commit()
        logger.info(f"[CouponGroups] 🗑 Группа «{group.name}» удалена")
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[CouponGroups] ❌ Ошибка при удалении группы: {e}")
        return False



async def add_coupon_to_group(
    session: AsyncSession,
    group_id: int,
    code: str,
    amount: int = 0,
    days: int | None = None,
    usage_limit: int = 1,
) -> bool:
    try:
        exists = await session.scalar(select(CouponGroupItem.id).where(CouponGroupItem.code == code))
        if exists:
            logger.warning(f"[CouponGroups] ⚠️ Купон с кодом {code} уже существует")
            return False
        item = CouponGroupItem(
            group_id=group_id,
            code=code,
            amount=amount,
            days=days,
            usage_limit=usage_limit,
        )
        session.add(item)
        await session.commit()
        group = await session.get(CouponGroup, group_id)
        group_name = group.name if group else f"ID:{group_id}"
        logger.info(f"[CouponGroups] ✅ Купон {code} добавлен в группу «{group_name}»")
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[CouponGroups] ❌ Ошибка при добавлении купона {code}: {e}")
        return False


async def get_group_item_by_code(session: AsyncSession, code: str) -> CouponGroupItem | None:
    stmt = select(CouponGroupItem).where(CouponGroupItem.code == code)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_group_items(session: AsyncSession, group_id: int) -> list[CouponGroupItem]:
    stmt = select(CouponGroupItem).where(CouponGroupItem.group_id == group_id)
    result = await session.execute(stmt)
    return result.scalars().all()

async def update_group_coupon_usage_count(session: AsyncSession, item_id: int):
    try:
        await session.execute(
            update(CouponGroupItem)
            .where(CouponGroupItem.id == item_id)
            .values(
                usage_count=CouponGroupItem.usage_count + 1,
                is_used=case(
                    (CouponGroupItem.usage_count + 1 >= CouponGroupItem.usage_limit, True),
                    else_=False
                ),
            )
        )
        await session.commit()
        logger.info(f"[CouponGroups] 🔁 Обновлён счётчик купона {item_id}")
    except SQLAlchemyError as e:
        logger.error(f"[CouponGroups] ❌ Ошибка при обновлении купона {item_id}: {e}")
        await session.rollback()


async def check_user_used_group(session: AsyncSession, group_id: int, user_id: int) -> bool:
    stmt = select(CouponGroupUsage).where(
        CouponGroupUsage.group_id == group_id,
        CouponGroupUsage.user_id == user_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None

async def create_group_usage(session: AsyncSession, group_id: int, user_id: int, item_id: int):
    try:
        stmt = insert(CouponGroupUsage).values(
            group_id=group_id,
            user_id=user_id,
            coupon_item_id=item_id,
            used_at=datetime.utcnow()
        )
        await session.execute(stmt)
        await session.commit()
        group = await session.get(CouponGroup, group_id)
        group_name = group.name if group else f"ID:{group_id}"
        logger.info(f"[CouponGroups] ✅ Пользователь {user_id} использовал купон из группы «{group_name}»")
    except SQLAlchemyError as e:
        logger.error(f"[CouponGroups] ❌ Ошибка при сохранении использования: {e}")
        await session.rollback()

async def get_group_usage_stats(session: AsyncSession, group_id: int) -> dict:
    try:
        total_coupons_stmt = select(func.count()).select_from(CouponGroupItem).where(
            CouponGroupItem.group_id == group_id
        )
        total_coupons = await session.scalar(total_coupons_stmt) or 0
        activated_stmt = select(func.count()).select_from(CouponGroupItem).where(
            CouponGroupItem.group_id == group_id,
            CouponGroupItem.usage_count > 0
        )
        activated_coupons = await session.scalar(activated_stmt) or 0

        users_stmt = select(func.count(func.distinct(CouponGroupUsage.user_id))).where(
            CouponGroupUsage.group_id == group_id
        )
        unique_users = await session.scalar(users_stmt) or 0

        return {
            "total_coupons": total_coupons,
            "activated_coupons": activated_coupons,
            "remaining_coupons": total_coupons - activated_coupons,
            "unique_users": unique_users,
        }
    except SQLAlchemyError as e:
        logger.error(f"[CouponGroups] ❌ Ошибка при получении статистики: {e}")
        return {
            "total_coupons": 0,
            "activated_coupons": 0,
            "remaining_coupons": 0,
            "unique_users": 0,
        }


async def get_group_usage_count(session: AsyncSession, group_id: int) -> int:
    try:
        stmt = select(func.count()).select_from(CouponGroupUsage).where(
            CouponGroupUsage.group_id == group_id
        )
        return await session.scalar(stmt) or 0
    except SQLAlchemyError as e:
        logger.error(f"[CouponGroups] ❌ Ошибка при подсчете использований: {e}")
        return 0




async def activate_group_coupon_atomic(
    session: AsyncSession,
    coupon_item_id: int,
    group_id: int,
    user_id: int,
    balance_update_func,
    payment_add_func,
) -> dict:
    try:
        coupon_item = await session.scalar(
            select(CouponGroupItem)
            .where(CouponGroupItem.id == coupon_item_id)
            .with_for_update()
        )

        if not coupon_item:
            return {"success": False, "error": "Купон не найден", "amount": None}

        if coupon_item.usage_count >= coupon_item.usage_limit:
            return {"success": False, "error": "Лимит активаций исчерпан", "amount": None}

        existing_usage = await session.scalar(
            select(CouponGroupUsage)
            .where(
                CouponGroupUsage.group_id == group_id,
                CouponGroupUsage.user_id == user_id
            )
            .with_for_update()
        )

        if existing_usage:
            return {"success": False, "error": "Вы уже использовали купон из этой группы", "amount": None}

        await balance_update_func(session, user_id, coupon_item.amount)

        await session.execute(
            update(CouponGroupItem)
            .where(CouponGroupItem.id == coupon_item_id)
            .values(
                usage_count=CouponGroupItem.usage_count + 1,
                is_used=case(
                    (CouponGroupItem.usage_count + 1 >= CouponGroupItem.usage_limit, True),
                    else_=False
                ),
            )
        )

        await session.execute(
            insert(CouponGroupUsage).values(
                group_id=group_id,
                user_id=user_id,
                coupon_item_id=coupon_item_id,
                used_at=datetime.utcnow()
            )
        )

        await payment_add_func(
            session,
            tg_id=user_id,
            amount=coupon_item.amount,
            payment_system="coupon_group"
        )

        logger.info(
            f"[CouponGroups] ✅ Атомарная активация: пользователь {user_id}, "
            f"купон {coupon_item_id}, сумма {coupon_item.amount}"
        )

        return {"success": True, "error": None, "amount": coupon_item.amount}

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[CouponGroups] ❌ Ошибка при атомарной активации купона: {e}")
        return {"success": False, "error": "Ошибка базы данных", "amount": None}


async def extend_key_with_group_coupon_atomic(
    session: AsyncSession,
    coupon_item_id: int,
    group_id: int,
    user_id: int,
    client_id: str,
    renew_func,
    update_expiry_func,
) -> dict:
    try:
        from database.models import Key

        coupon_item = await session.scalar(
            select(CouponGroupItem)
            .where(CouponGroupItem.id == coupon_item_id)
            .with_for_update()
        )

        if not coupon_item or not coupon_item.days:
            return {"success": False, "error": "Купон не найден или не содержит дни", "new_expiry": None, "days": None}

        if coupon_item.usage_count >= coupon_item.usage_limit:
            return {"success": False, "error": "Лимит активаций исчерпан", "new_expiry": None, "days": None}

        existing_usage = await session.scalar(
            select(CouponGroupUsage)
            .where(
                CouponGroupUsage.group_id == group_id,
                CouponGroupUsage.user_id == user_id
            )
            .with_for_update()
        )

        if existing_usage:
            return {"success": False, "error": "Вы уже использовали купон из этой группы", "new_expiry": None, "days": None}

        key = await session.scalar(
            select(Key)
            .where(Key.tg_id == user_id, Key.client_id == client_id)
            .with_for_update()
        )

        if not key or key.is_frozen:
            return {"success": False, "error": "Ключ не найден или заморожен", "new_expiry": None, "days": None}

        now_ms = int(datetime.now().timestamp() * 1000)
        current_expiry = key.expiry_time
        new_expiry = max(now_ms, current_expiry) + (coupon_item.days * 86400 * 1000)

        await session.execute(
            update(CouponGroupItem)
            .where(CouponGroupItem.id == coupon_item_id)
            .values(
                usage_count=CouponGroupItem.usage_count + 1,
                is_used=case(
                    (CouponGroupItem.usage_count + 1 >= CouponGroupItem.usage_limit, True),
                    else_=False
                ),
            )
        )

        await session.execute(
            insert(CouponGroupUsage).values(
                group_id=group_id,
                user_id=user_id,
                coupon_item_id=coupon_item_id,
                used_at=datetime.utcnow()
            )
        )

        await session.commit()

        logger.info(
            f"[CouponGroups] ✅ Атомарное продление: пользователь {user_id}, "
            f"купон {coupon_item_id}, ключ {client_id}, дни {coupon_item.days}"
        )

        return {
            "success": True,
            "error": None,
            "new_expiry": new_expiry,
            "days": coupon_item.days
        }

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[CouponGroups] ❌ Ошибка при атомарном продлении ключа: {e}")
        return {"success": False, "error": "Ошибка базы данных", "new_expiry": None, "days": None}
