import html
from datetime import datetime
import random
import string

import re
import pytz
from aiogram import F, Router
from handlers.coupons import CouponActivationState
from handlers.coupons import activate_coupon
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from config import ADMIN_ID
from database import (
    add_payment,
    add_user,
    check_user_exists,
    get_keys,
    get_tariff_by_id,
    update_balance,
    update_key_expiry,
)
from filters.admin import IsAdminFilter
from handlers.keys.operations import renew_key_in_cluster
from handlers.payments.currency_rates import format_for_user
from handlers.profile import process_callback_view_profile
from handlers.utils import format_days
from hooks.hooks import register_hook
from logger import logger

from . import db
from . import texts
from .settings import GROUPS_PER_PAGE, COUPONS_PER_PAGE


# Добавьте эту функцию для генерации случайных кодов
def generate_random_code(length=10):
    """Генерирует случайный код из букв и цифр"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def natural_sort_key(text):
    def atoi(s):
        return int(s) if s.isdigit() else s
    return [atoi(c) for c in re.split(r"(\d+)", str(text))]

def _build_group_management_keyboard(group_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_ADD_COUPONS, callback_data=f"admin_add_coupons|{group_id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_DELETE_GROUP, callback_data=f"admin_delete_group_confirm|{group_id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin_view_coupon_groups"))
    return builder.as_markup()

def _build_back_keyboard(callback_data: str):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data=callback_data))
    return builder.as_markup()

def _build_success_keyboard(group_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить еще", callback_data=f"admin_add_coupons|{group_id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_VIEW_DETAILS, callback_data=f"admin_view_group_detail|{group_id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin_view_coupon_groups"))
    return builder.as_markup()

# Измените функцию _create_coupons_bulk
async def _create_coupons_bulk(
    session: AsyncSession,
    group_id: int,
    group_name: str,
    prefix: str,
    count: int,
    amount: int = 0,
    days: int = None,
    usage_limit: int = 1,
) -> tuple[list[str], list[str]]:
    created_codes = []
    skipped_codes = []

    for i in range(count):
        # Генерируем случайный код
        random_part = generate_random_code(10)
        code = f"{prefix}{random_part}"
        
        success = await db.add_coupon_to_group(
            session, group_id, code, amount, days, usage_limit
        )
        if success:
            created_codes.append(code)
        else:
            skipped_codes.append(code)

    return created_codes, skipped_codes


def _format_creation_result_message(
    group_name: str,
    created_codes: list[str],
    skipped_codes: list[str],
) -> str:
    if created_codes and not skipped_codes:
        codes_str = ", ".join(created_codes[:10])
        if len(created_codes) > 10:
            codes_str += f" ... (+{len(created_codes) - 10} еще)"
        return texts.COUPONS_ADDED.format(
            group_name=group_name,
            count=len(created_codes),
            codes=codes_str
        )

    elif created_codes and skipped_codes:
        created_str = ", ".join(created_codes[:5])
        if len(created_codes) > 5:
            created_str += f" ... (+{len(created_codes) - 5} еще)"

        skipped_str = ", ".join(skipped_codes[:5])
        if len(skipped_codes) > 5:
            skipped_str += f" ... (+{len(skipped_codes) - 5} еще)"

        return (
            f"✅ <b>Добавлено купонов в группу «{group_name}»: {len(created_codes)}</b>\n"
            f"<code>{created_str}</code>\n\n"
            f"⚠️ <b>Пропущено (уже существуют): {len(skipped_codes)}</b>\n"
            f"<code>{skipped_str}</code>"
        )

    else:
        skipped_str = ", ".join(skipped_codes[:10])
        if len(skipped_codes) > 10:
            skipped_str += f" ... (+{len(skipped_codes) - 10} еще)"

        return (
            f"⚠️ <b>Купоны уже существуют и не были добавлены:</b>\n"
            f"<code>{skipped_str}</code>\n\n"
            f"Попробуйте использовать другой префикс или номера."
        )


async def _activate_group_coupon(
    session: AsyncSession,
    coupon_item,
    user_id: int,
    message: Message,
    state: FSMContext,
    user_data: dict = None,
) -> bool:
    has_used = await db.check_user_used_group(session, coupon_item.group_id, user_id)
    if has_used:
        await message.answer(texts.GROUP_ALREADY_USED)
        await state.clear()
        return False

    if coupon_item.usage_count >= coupon_item.usage_limit:
        await message.answer(texts.COUPON_LIMIT_REACHED)
        await state.clear()
        return False

    if not await check_user_exists(session, user_id):
        if user_data:
            await add_user(session=session, **user_data)
        else:
            await add_user(
                session=session,
                tg_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                language_code=message.from_user.language_code,
            )

    if coupon_item.amount > 0:
        await update_balance(session, user_id, coupon_item.amount)
        await db.update_group_coupon_usage_count(session, coupon_item.id)
        await db.create_group_usage(session, coupon_item.group_id, user_id, coupon_item.id)

        language_code = user_data.get("language_code") if user_data else message.from_user.language_code
        formatted_amount = await format_for_user(session, user_id, coupon_item.amount, language_code)
        await message.answer(texts.COUPON_BALANCE_ACTIVATED.format(amount=formatted_amount))
        await state.clear()
        return True

    elif coupon_item.days:
        await state.update_data(
            coupon_item_id=coupon_item.id,
            coupon_days=coupon_item.days,
            coupon_group_id=coupon_item.group_id
        )

        keys = await get_keys(session, user_id)
        active_keys = [k for k in keys if not k.is_frozen]

        if not active_keys:
            await message.answer(texts.NO_KEYS_FOR_EXTENSION)
            await state.clear()
            return False

        builder = InlineKeyboardBuilder()
        moscow_tz = pytz.timezone("Europe/Moscow")
        response_message = texts.COUPONS_DAYS_MESSAGE

        for key in active_keys:
            key_display = html.escape((key.alias or key.email).strip())
            expiry_date = datetime.fromtimestamp(key.expiry_time / 1000, tz=moscow_tz).strftime("до %d.%m.%y, %H:%M")
            response_message += f"• <b>{key_display}</b> ({expiry_date})\n"
            builder.button(
                text=key_display,
                callback_data=f"group_extend_key|{key.client_id}",
            )

        response_message += "</blockquote>"
        builder.button(text=texts.BTN_CANCEL, callback_data="profile")
        builder.adjust(1)

        await message.answer(response_message, reply_markup=builder.as_markup())
        await state.set_state(GroupCouponActivationState.waiting_for_key_selection)
        return True

    return False



class GroupCouponActivationState(StatesGroup):
    waiting_for_coupon_code = State()
    waiting_for_key_selection = State()


class AdminGroupCouponState(StatesGroup):
    waiting_for_group_name = State()
    waiting_for_coupon_type = State()
    waiting_for_balance_data = State()
    waiting_for_days_data = State()


router = Router(name="coupon_groups_module")




@router.message(CouponActivationState.waiting_for_coupon_code, F.text & ~F.text.startswith("/"))
async def intercept_coupon_activation(message: Message, state: FSMContext, session: AsyncSession):
    coupon_code = message.text.strip()
    coupon_item = await db.get_group_item_by_code(session, coupon_code)

    if not coupon_item:
        logger.info(f"[CouponGroups] Купон {coupon_code} не из группы, передаём в стандартный обработчик")
        await activate_coupon(message, state, session, coupon_code)
        return

    logger.info(f"[CouponGroups] Активация купона из группы: {coupon_code}")

    await _activate_group_coupon(session, coupon_item, message.from_user.id, message, state)



@router.message(GroupCouponActivationState.waiting_for_coupon_code, F.text & ~F.text.startswith("/"))
async def process_group_coupon_code(message: Message, state: FSMContext, session: AsyncSession):
    coupon_code = message.text.strip()
    logger.info(f"[CouponGroups] Активация купона: {coupon_code}")
    coupon_item = await db.get_group_item_by_code(session, coupon_code)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_PROFILE, callback_data="profile"))

    if not coupon_item:
        await message.answer(texts.COUPON_NOT_FOUND, reply_markup=builder.as_markup())
        return

    if coupon_item.usage_count >= coupon_item.usage_limit or coupon_item.is_used:
        await message.answer(texts.COUPON_EXHAUSTED, reply_markup=builder.as_markup())
        return

    user_id = message.from_user.id

    has_used = await db.check_user_used_group(session, coupon_item.group_id, user_id)
    if has_used:
        await message.answer(texts.GROUP_ALREADY_USED)
        await state.clear()
        return

    user_exists = await check_user_exists(session, user_id)
    if not user_exists:
        await add_user(
            session=session,
            tg_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
            is_bot=False,
        )

    group = await db.get_coupon_group_by_id(session, coupon_item.group_id)
    group_name = group.name if group else "неизвестная группа"

    if coupon_item.amount > 0:
        try:
            result = await db.activate_group_coupon_atomic(
                session=session,
                coupon_item_id=coupon_item.id,
                group_id=coupon_item.group_id,
                user_id=user_id,
                balance_update_func=update_balance,
                payment_add_func=add_payment,
            )

            if not result["success"]:
                await message.answer(f"❌ {result['error']}")
                await state.clear()
                return

            amount_txt = await format_for_user(session, user_id, result["amount"], message.from_user.language_code)
            await message.answer(
                texts.COUPON_BALANCE_ACTIVATED.format(amount=amount_txt, group_name=group_name)
            )
            await state.clear()
        except Exception as e:
            logger.error(f"[CouponGroups] Ошибка при активации купона на баланс: {e}")
            await message.answer(texts.ERROR_ACTIVATING_COUPON)
            await state.clear()
        return

    if coupon_item.days:
        try:
            keys = await get_keys(session, user_id)
            active_keys = [k for k in keys if not k.is_frozen]

            if not active_keys:
                await message.answer(texts.NO_ACTIVE_KEYS)
                await state.clear()
                return

            moscow_tz = pytz.timezone("Europe/Moscow")
            keys_list = ""
            builder = InlineKeyboardBuilder()

            for key in active_keys:
                key_display = html.escape((key.alias or key.email).strip())
                expiry_date = datetime.fromtimestamp(key.expiry_time / 1000, tz=moscow_tz).strftime("до %d.%m.%y, %H:%M")
                keys_list += f"• <b>{key_display}</b> ({expiry_date})\n"
                builder.button(
                    text=key_display,
                    callback_data=f"extend_group_key|{key.client_id}|{coupon_item.id}",
                )

            builder.button(text=texts.BTN_CANCEL, callback_data="cancel_group_coupon_activation")
            builder.adjust(1)

            await message.answer(
                texts.SELECT_KEY_TO_EXTEND.format(days=format_days(coupon_item.days), keys_list=keys_list),
                reply_markup=builder.as_markup(),
            )
            await state.set_state(GroupCouponActivationState.waiting_for_key_selection)
            await state.update_data(coupon_item_id=coupon_item.id, user_id=user_id)
        except Exception as e:
            logger.error(f"[CouponGroups] Ошибка при обработке купона на дни: {e}")
            await message.answer(texts.ERROR_ACTIVATING_COUPON)
            await state.clear()
        return

    await message.answer(texts.COUPON_INVALID)
    await state.clear()


@router.callback_query(F.data.startswith("extend_group_key|"))
async def handle_group_key_extension(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    from database.models import Key
    parts = callback_query.data.split("|")
    client_id = parts[1]
    coupon_item_id = int(parts[2])
    tg_id = callback_query.from_user.id

    try:
        result = await db.extend_key_with_group_coupon_atomic(
            session=session,
            coupon_item_id=coupon_item_id,
            group_id=data.get("coupon_group_id"),
            user_id=tg_id,
            client_id=client_id,
            renew_func=renew_key_in_cluster,
            update_expiry_func=update_key_expiry,
        )

        if not result["success"]:
            await callback_query.message.edit_text(f"❌ {result['error']}")
            await state.clear()
            return

        new_expiry = result["new_expiry"]
        days = result["days"]

        key = await session.scalar(
            db.select(Key).where(Key.tg_id == tg_id, Key.client_id == client_id)
        )

        if key:
            tariff = None
            if key.tariff_id:
                tariff = await get_tariff_by_id(session, key.tariff_id)
            total_gb = int(tariff["traffic_limit"]) if tariff and tariff.get("traffic_limit") else 0
            device_limit = int(tariff["device_limit"]) if tariff and tariff.get("device_limit") else 0

            await renew_key_in_cluster(
                cluster_id=key.server_id,
                email=key.email,
                client_id=client_id,
                new_expiry_time=new_expiry,
                total_gb=total_gb,
                session=session,
                hwid_device_limit=device_limit,
                reset_traffic=False,
            )
            await update_key_expiry(session, client_id, new_expiry)

            alias = key.alias or key.email
            expiry_date = datetime.fromtimestamp(new_expiry / 1000, tz=pytz.timezone("Europe/Moscow")).strftime("%d.%m.%y, %H:%M")

            coupon_item = await session.scalar(
                db.select(db.CouponGroupItem).where(db.CouponGroupItem.id == coupon_item_id)
            )
            group = await db.get_coupon_group_by_id(session, coupon_item.group_id)
            group_name = group.name if group else "неизвестная группа"

            await callback_query.message.answer(
                texts.COUPON_DAYS_ACTIVATED.format(
                    alias=alias,
                    days=format_days(days),
                    expiry=expiry_date,
                    group_name=group_name,
                )
            )
            is_admin = callback_query.from_user.id in ADMIN_ID
            await process_callback_view_profile(callback_query.message, state, admin=is_admin, session=session)
            await state.clear()
        else:
            await callback_query.message.edit_text("❌ Ошибка: ключ не найден после валидации")
            await state.clear()

    except Exception as e:
        logger.error(f"[CouponGroups] Ошибка при продлении ключа: {e}")
        await callback_query.message.edit_text(texts.ERROR_ACTIVATING_COUPON)
        await state.clear()



@router.callback_query(F.data.startswith("group_extend_key|"), GroupCouponActivationState.waiting_for_key_selection)
async def handle_group_extend_key_from_intercept(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    from database.models import Key
    
    parts = callback_query.data.split("|")
    client_id = parts[1]
    tg_id = callback_query.from_user.id
    
    data = await state.get_data()
    coupon_item_id = data.get("coupon_item_id")
    
    if not coupon_item_id:
        await callback_query.message.edit_text("❌ Ошибка: данные купона не найдены")
        await state.clear()
        return
    
    try:
        result = await db.extend_key_with_group_coupon_atomic(
            session=session,
            coupon_item_id=coupon_item_id,
            group_id=data.get("coupon_group_id"),
            user_id=tg_id,
            client_id=client_id,
            renew_func=renew_key_in_cluster,
            update_expiry_func=update_key_expiry,
        )

        if not result["success"]:
            await callback_query.message.edit_text(f"❌ {result['error']}")
            await state.clear()
            return

        new_expiry = result["new_expiry"]
        days = result["days"]

        key = await session.scalar(
            db.select(Key).where(Key.tg_id == tg_id, Key.client_id == client_id)
        )

        if key:
            tariff = None
            if key.tariff_id:
                tariff = await get_tariff_by_id(session, key.tariff_id)
            total_gb = int(tariff["traffic_limit"]) if tariff and tariff.get("traffic_limit") else 0
            device_limit = int(tariff["device_limit"]) if tariff and tariff.get("device_limit") else 0

            await renew_key_in_cluster(
                cluster_id=key.server_id,
                email=key.email,
                client_id=client_id,
                new_expiry_time=new_expiry,
                total_gb=total_gb,
                session=session,
                hwid_device_limit=device_limit,
                reset_traffic=False,
            )
            await update_key_expiry(session, client_id, new_expiry)

            alias = key.alias or key.email
            expiry_date = datetime.fromtimestamp(new_expiry / 1000, tz=pytz.timezone("Europe/Moscow")).strftime("%d.%m.%y, %H:%M")

            coupon_item = await session.scalar(
                db.select(db.CouponGroupItem).where(db.CouponGroupItem.id == coupon_item_id)
            )
            group = await db.get_coupon_group_by_id(session, coupon_item.group_id)
            group_name = group.name if group else "неизвестная группа"

            await callback_query.message.answer(
                texts.COUPON_DAYS_ACTIVATED.format(
                    alias=alias,
                    days=format_days(days),
                    expiry=expiry_date,
                    group_name=group_name,
                )
            )
            is_admin = callback_query.from_user.id in ADMIN_ID
            await process_callback_view_profile(callback_query.message, state, admin=is_admin, session=session)
            await state.clear()
        else:
            await callback_query.message.edit_text("❌ Ошибка: ключ не найден после валидации")
            await state.clear()

    except Exception as e:
        logger.error(f"[CouponGroups] Ошибка при продлении ключа из intercept: {e}")
        await callback_query.message.edit_text(texts.ERROR_ACTIVATING_COUPON)
        await state.clear()

@router.callback_query(F.data == "cancel_group_coupon_activation")
async def cancel_group_coupon_activation(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    await callback_query.message.edit_text(texts.ACTIVATION_CANCELLED)
    is_admin = callback_query.from_user.id in ADMIN_ID
    await process_callback_view_profile(callback_query.message, state, admin=is_admin, session=session)
    await state.clear()

@router.callback_query(F.data == "exit_group_coupon_input")
async def handle_exit_group_coupon_input(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    await state.clear()
    is_admin = callback_query.from_user.id in ADMIN_ID
    await process_callback_view_profile(callback_query.message, state, admin=is_admin, session=session)


@router.callback_query(F.data == "admin_coupon_groups", IsAdminFilter())
async def handle_admin_coupon_groups_menu(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_CREATE_GROUP, callback_data="admin_create_coupon_group"))
    builder.row(InlineKeyboardButton(text=texts.BTN_VIEW_GROUPS, callback_data="admin_view_coupon_groups"))
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin"))
    await callback_query.message.edit_text(
        text=texts.ADMIN_MENU_TITLE,
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "admin_create_coupon_group", IsAdminFilter())
async def handle_create_coupon_group(callback_query: CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="admin_coupon_groups"))
    await callback_query.message.edit_text(
        text=texts.CREATE_GROUP_NAME_PROMPT,
        reply_markup=builder.as_markup(),
    )
    await state.set_state(AdminGroupCouponState.waiting_for_group_name)


@router.message(AdminGroupCouponState.waiting_for_group_name, F.text & ~F.text.startswith("/"), IsAdminFilter())
async def process_group_name(message: Message, state: FSMContext, session: AsyncSession):
    group_name = message.text.strip()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin_coupon_groups"))

    if len(group_name) > 20:
        await message.answer(
            texts.GROUP_NAME_TOO_LONG.format(length=len(group_name)),
            reply_markup=builder.as_markup()
        )
        return

    group = await db.create_coupon_group(session, group_name)

    if not group:
        await message.answer(texts.GROUP_ALREADY_EXISTS, reply_markup=builder.as_markup())
        return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_ADD_COUPONS, callback_data=f"admin_add_coupons|{group.id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin_coupon_groups"))

    await message.answer(
        texts.GROUP_CREATED.format(name=group_name),
        reply_markup=builder.as_markup(),
    )
    await state.clear()


@router.callback_query(F.data.startswith("admin_add_coupons|"), IsAdminFilter())
async def handle_add_coupons(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession):
    group_id = int(callback_query.data.split("|")[1])
    group = await db.get_coupon_group_by_id(session, group_id)
    if not group:
        await callback_query.message.edit_text("❌ Группа не найдена")
        return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_BALANCE_TYPE, callback_data=f"coupon_type_balance|{group_id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_DAYS_TYPE, callback_data=f"coupon_type_days|{group_id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data=f"admin_view_group_detail|{group_id}"))

    await callback_query.message.edit_text(
        text=texts.COUPON_TYPE_SELECTION.format(group_name=group.name),
        reply_markup=builder.as_markup(),
    )
    await state.set_state(AdminGroupCouponState.waiting_for_coupon_type)
    await state.update_data(group_id=group_id, group_name=group.name)


@router.callback_query(F.data.startswith("coupon_type_balance|"), IsAdminFilter())
async def handle_balance_coupon_type(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession):
    group_id = int(callback_query.data.split("|")[1])
    data = await state.get_data()
    group_name = data.get("group_name", "")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data=f"admin_add_coupons|{group_id}"))

    await callback_query.message.edit_text(
        text=texts.ADD_BALANCE_COUPONS_PROMPT.format(group_name=group_name),
        reply_markup=builder.as_markup(),
    )
    await state.set_state(AdminGroupCouponState.waiting_for_balance_data)


@router.callback_query(F.data.startswith("coupon_type_days|"), IsAdminFilter())
async def handle_days_coupon_type(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession):
    group_id = int(callback_query.data.split("|")[1])
    data = await state.get_data()
    group_name = data.get("group_name", "")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data=f"admin_add_coupons|{group_id}"))

    await callback_query.message.edit_text(
        text=texts.ADD_DAYS_COUPONS_PROMPT.format(group_name=group_name),
        reply_markup=builder.as_markup(),
    )
    await state.set_state(AdminGroupCouponState.waiting_for_days_data)


@router.message(AdminGroupCouponState.waiting_for_balance_data, F.text & ~F.text.startswith("/"), IsAdminFilter())
async def process_balance_coupons_data(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    group_id = data["group_id"]
    group_name = data["group_name"]
    parts = message.text.strip().split()

    if len(parts) != 4:
        await message.answer(
            "❌ <b>Неверный формат!</b>\n\n"
            "Используйте: <code>ПРЕФИКС количество сумма лимит</code>\n"
            "Пример: <code>WINTER 10 100 1</code>",
            reply_markup=_build_back_keyboard(f"admin_view_group_detail|{group_id}")
        )
        return

    try:
        prefix = parts[0]

        try:
            count = int(parts[1])
        except ValueError:
            raise ValueError(f"Количество должно быть числом, а не '{parts[1]}'")

        try:
            amount = int(parts[2])
        except ValueError:
            raise ValueError(f"Сумма должна быть числом, а не '{parts[2]}'")

        try:
            usage_limit = int(parts[3])
        except ValueError:
            raise ValueError(f"Лимит должен быть числом, а не '{parts[3]}'")

        if amount <= 0:
            raise ValueError("Сумма должна быть больше 0")
        if count <= 0 or count > 1000:
            raise ValueError("Количество должно быть от 1 до 1000")
        if usage_limit <= 0:
            raise ValueError("Лимит должен быть больше 0")

        created_codes, skipped_codes = await _create_coupons_bulk(
            session, group_id, group_name, prefix, count,
            amount=amount, usage_limit=usage_limit
        )

        result_message = _format_creation_result_message(group_name, created_codes, skipped_codes)

        await message.answer(result_message, reply_markup=_build_success_keyboard(group_id))
        await state.clear()

    except ValueError as e:
        await message.answer(
            f"❌ <b>Ошибка:</b> {str(e)}\n\n"
            "Проверьте правильность ввода!",
            reply_markup=_build_back_keyboard(f"admin_view_group_detail|{group_id}")
        )
    except Exception as e:
        logger.error(f"Ошибка при создании купонов: {e}")
        await message.answer(
            texts.ERROR_ADDING_COUPONS,
            reply_markup=_build_back_keyboard(f"admin_view_group_detail|{group_id}")
        )


@router.message(AdminGroupCouponState.waiting_for_days_data, F.text & ~F.text.startswith("/"), IsAdminFilter())
async def process_days_coupons_data(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    group_id = data["group_id"]
    group_name = data["group_name"]
    parts = message.text.strip().split()

    if len(parts) != 4:
        await message.answer(
            "❌ <b>Неверный формат!</b>\n\n"
            "Используйте: <code>ПРЕФИКС количество дни лимит</code>\n"
            "Пример: <code>SUMMER 5 30 1</code>",
            reply_markup=_build_back_keyboard(f"admin_view_group_detail|{group_id}")
        )
        return

    try:
        prefix = parts[0]

        try:
            count = int(parts[1])
        except ValueError:
            raise ValueError(f"Количество должно быть числом, а не '{parts[1]}'")

        try:
            days = int(parts[2])
        except ValueError:
            raise ValueError(f"Дни должны быть числом, а не '{parts[2]}'")

        try:
            usage_limit = int(parts[3])
        except ValueError:
            raise ValueError(f"Лимит должен быть числом, а не '{parts[3]}'")

        if days <= 0:
            raise ValueError("Количество дней должно быть больше 0")
        if count <= 0 or count > 1000:
            raise ValueError("Количество должно быть от 1 до 1000")
        if usage_limit <= 0:
            raise ValueError("Лимит должен быть больше 0")

        created_codes, skipped_codes = await _create_coupons_bulk(
            session, group_id, group_name, prefix, count,
            days=days, usage_limit=usage_limit
        )

        result_message = _format_creation_result_message(group_name, created_codes, skipped_codes)

        await message.answer(result_message, reply_markup=_build_success_keyboard(group_id))
        await state.clear()

    except ValueError as e:
        await message.answer(
            f"❌ <b>Ошибка:</b> {str(e)}\n\n"
            "Проверьте правильность ввода!",
            reply_markup=_build_back_keyboard(f"admin_view_group_detail|{group_id}")
        )
    except Exception as e:
        logger.error(f"Ошибка при создании купонов: {e}")
        await message.answer(
            texts.ERROR_ADDING_COUPONS,
            reply_markup=_build_back_keyboard(f"admin_view_group_detail|{group_id}")
        )
@router.callback_query(F.data == "admin_view_coupon_groups", IsAdminFilter())
@router.callback_query(F.data.startswith("admin_view_coupon_groups_page|"), IsAdminFilter())
async def handle_view_coupon_groups(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    if "|" in callback_query.data:
        page = int(callback_query.data.split("|")[1])
    else:
        page = 1
    result = await db.get_all_coupon_groups(session, page, GROUPS_PER_PAGE)
    groups = result["groups"]
    total_pages = result["pages"]

    if not groups:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin_coupon_groups"))
        await callback_query.message.edit_text(
            text=texts.NO_GROUPS,
            reply_markup=builder.as_markup(),
        )
        return

    text = texts.GROUPS_LIST_TITLE.format(page=page, total_pages=total_pages)

    builder = InlineKeyboardBuilder()
    for group_data in groups:
        group_id = group_data["id"]
        group_name = group_data["name"]

        stats = await db.get_group_usage_stats(session, group_id)

        text += texts.GROUP_ITEM.format(
            name=group_name,
            total=stats["total_coupons"],
            used=stats["activated_coupons"],
        )

        builder.row(InlineKeyboardButton(
            text=f"📂 {group_name}",
            callback_data=f"admin_view_group_detail|{group_id}"
        ))

    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(
            text="◀️ Пред",
            callback_data=f"admin_view_coupon_groups_page|{page - 1}"
        ))
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(
            text="След ▶️",
            callback_data=f"admin_view_coupon_groups_page|{page + 1}"
        ))

    if pagination_row:
        builder.row(*pagination_row)

    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin_coupon_groups"))

    await callback_query.message.edit_text(text=text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin_view_group_detail|"), IsAdminFilter())
async def handle_view_group_detail(callback_query: CallbackQuery, session: AsyncSession):
    from config import USERNAME_BOT

    parts = callback_query.data.split("|")
    group_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1
    group = await db.get_coupon_group_by_id(session, group_id)
    if not group:
        await callback_query.message.edit_text("❌ Группа не найдена")
        return

    stats = await db.get_group_usage_stats(session, group_id)
    coupons = await db.get_group_items(session, group_id)

    coupons = sorted(coupons, key=lambda c: natural_sort_key(c.code))

    per_page = COUPONS_PER_PAGE
    total_coupons = len(coupons)
    total_pages = (total_coupons + per_page - 1) // per_page if total_coupons > 0 else 1

    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_coupons = coupons[start_idx:end_idx]

    text = texts.GROUP_DETAIL_TITLE.format(
        name=group.name,
        total_coupons=stats["total_coupons"],
        activated_coupons=stats["activated_coupons"],
        remaining_coupons=stats["remaining_coupons"],
        unique_users=stats["unique_users"],
    )

    if coupons:
        if total_pages > 1:
            text += f"\n<b>📄 Страница {page} из {total_pages}</b>\n"
        text += texts.COUPONS_IN_GROUP_TITLE

        for coupon in page_coupons:
            coupon_type = f"{coupon.amount}₽" if coupon.amount > 0 else f"{coupon.days}d"
            text += texts.COUPON_ITEM.format(
                code=coupon.code,
                type=coupon_type,
                usage_count=coupon.usage_count,
                usage_limit=coupon.usage_limit,
            )

        text += texts.COUPON_LINK_TEMPLATE.format(bot_username=USERNAME_BOT)

    builder = InlineKeyboardBuilder()

    if total_pages > 1:
        pagination_buttons = []
        if page > 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"admin_view_group_detail|{group_id}|{page - 1}"
                )
            )
        if page < total_pages:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="Вперед ➡️",
                    callback_data=f"admin_view_group_detail|{group_id}|{page + 1}"
                )
            )
        if pagination_buttons:
            builder.row(*pagination_buttons)

    builder.row(InlineKeyboardButton(text=texts.BTN_ADD_COUPONS, callback_data=f"admin_add_coupons|{group_id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_DELETE_GROUP, callback_data=f"admin_delete_group_confirm|{group_id}"))
    builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin_view_coupon_groups"))

    await callback_query.message.edit_text(text=text, reply_markup=builder.as_markup())
@router.callback_query(F.data.startswith("admin_delete_group_confirm|"), IsAdminFilter())
async def handle_delete_group_confirm(callback_query: CallbackQuery, session: AsyncSession):
    group_id = int(callback_query.data.split("|")[1])
    group = await db.get_coupon_group_by_id(session, group_id)
    if not group:
        await callback_query.message.edit_text("❌ Группа не найдена")
        return

    stats = await db.get_group_usage_stats(session, group_id)
    total_usages = await db.get_group_usage_count(session, group_id)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=texts.BTN_CONFIRM_DELETE,
        callback_data=f"admin_delete_group|{group_id}"
    ))
    builder.row(InlineKeyboardButton(
        text=texts.BTN_CANCEL_DELETE,
        callback_data=f"admin_view_group_detail|{group_id}"
    ))

    await callback_query.message.edit_text(
        text=texts.CONFIRM_DELETE_GROUP.format(
            name=group.name,
            total_coupons=stats["total_coupons"],
            total_usages=total_usages,
        ),
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("admin_delete_group|"), IsAdminFilter())
async def handle_delete_group(callback_query: CallbackQuery, session: AsyncSession):
    group_id = int(callback_query.data.split("|")[1])
    group = await db.get_coupon_group_by_id(session, group_id)
    if not group:
        await callback_query.message.edit_text("❌ Группа не найдена")
        return

    group_name = group.name
    success = await db.delete_coupon_group(session, group_id)

    if success:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=texts.BTN_BACK, callback_data="admin_view_coupon_groups"))
        await callback_query.message.edit_text(
            text=texts.GROUP_DELETED.format(name=group_name),
            reply_markup=builder.as_markup(),
        )
    else:
        await callback_query.message.edit_text("❌ Ошибка при удалении группы")



def _build_admin_groups_button():
    return InlineKeyboardButton(
        text="🎫 Группы купонов",
        callback_data="admin_coupon_groups"
    )

async def admin_panel_hook(**kwargs):
    return {"button": _build_admin_groups_button()}

async def start_link_hook(**kwargs):
    part = kwargs.get("part", "")
    if "coupons" not in part:
        return None

    code = part.split("coupons")[1].strip("_")
    if not code:
        return None

    message = kwargs.get("message")
    state = kwargs.get("state")
    session = kwargs.get("session")
    user_data = kwargs.get("user_data")

    if not all([message, state, session, user_data]):
        return None

    coupon_item = await db.get_group_item_by_code(session, code)
    if not coupon_item:
        return None

    await _activate_group_coupon(
        session, coupon_item, user_data["tg_id"], message, state, user_data
    )

    return {"handled": True}

register_hook("admin_panel", admin_panel_hook)
register_hook("start_link", start_link_hook)
