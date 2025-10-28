# [file name]: router.py
# [file content begin]
import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from hooks.hooks import register_hook
from logger import logger

router = Router(name="manual_pay_module")
from hooks.hooks import register_hook as _reg

async def _start_hook(message=None, state=None, session=None, user_data=None, part: str = "", **kwargs):
    # deep-link: /start manualpay_approve_<uid>_<amount>_<sign>
    try:
        if not part or not part.startswith("manualpay_"):
            return None
        from .settings import SIGN_KEY
        tokens = part.split("_")
        action = tokens[1]
        if action not in ("approve", "reject"):
            return None
        user_id = int(tokens[2])
        amount = float(tokens[3])
        sign = tokens[4] if len(tokens) > 4 else ""
        if sign != SIGN_KEY:
            await message.answer("❌ Неверная ссылка.")
            return None

        # Проверяем, не был ли платеж уже обработан
        from database.payments import get_payment_by_user_amount
        existing_payment = await get_payment_by_user_amount(session, user_id, amount, "MANUAL")
        if existing_payment:
            await message.answer("⚠️ Этот платеж уже был обработан ранее.")
            return None
            
        # Эмулируем колбек, вызывая уже существующие обработчики
        class _Stub:
            def __init__(self, msg, data):
                self.message = msg
                self.data = data
                self.from_user = msg.from_user
                self.bot = msg.bot

        if action == "approve":
            await manualpay_approve(_Stub(message, f"manualpay|approve|{user_id}|{amount}"), session)
        else:
            await manualpay_reject(_Stub(message, f"manualpay|reject|{user_id}|{amount}"), session)
    except Exception as e:
        logger.error(f"[ManualPay] Ошибка deep-link обработки: {e}")
    return None

_reg("start_link", _start_hook)

class ManualPayStates(StatesGroup):
    waiting_amount_input = State()

def _build_pay_button():
    from .texts import BTN_MANUAL_PAY
    return InlineKeyboardButton(text=BTN_MANUAL_PAY, callback_data="manualpay|start")

def _providers_patch() -> dict[str, dict]:
    from .settings import ENABLE
    if not ENABLE:
        return {}
    return {"MANUAL": {"currency": "RUB", "value": "manualpay|start", "fast": None, "module": "manual_pay", "enabled": True}}

def _choose_details():
    from .settings import MODE, CARDS, SBP, REQUISITES, LINKS, MULTI_METHODS
    allowed = {"card", "sbp", "requisites", "link"}
    raw = MULTI_METHODS or []
    if isinstance(raw, str):
        candidates = [s.strip().lower() for s in raw.split(",")]
    else:
        candidates = [str(s).strip().lower() for s in raw]
    methods = [m for m in candidates if m in allowed]
    if methods:
        blocks: list[tuple[str, object]] = []
        for m in methods:
            if m == "card":
                blocks.append(("card", (random.choice(CARDS) if CARDS else "")))
            elif m == "sbp":
                if SBP:
                    sbp_details = random.choice(SBP)
                    blocks.append(("sbp", sbp_details))
                else:
                    blocks.append(("sbp", {"phone": "", "bank": ""}))
            elif m == "link":
                blocks.append(("link", (random.choice(LINKS) if LINKS else "")))
            else:
                blocks.append(("requisites", REQUISITES))
        return "multi", blocks

    if MODE == "card":
        return "card", (random.choice(CARDS) if CARDS else "")
    if MODE == "sbp":
        if SBP:
            sbp_details = random.choice(SBP)
            return "sbp", sbp_details
        return "sbp", {"phone": "", "bank": ""}
    if MODE == "link":
        return "link", (random.choice(LINKS) if LINKS else "")
    return "requisites", REQUISITES

@router.callback_query(F.data == "manualpay|start")
async def manualpay_start(callback: CallbackQuery, state: FSMContext):
    from .texts import CHOOSE_AMOUNT, BTN_BACK
    from handlers.texts import PAYMENT_OPTIONS
    from handlers.utils import edit_or_send_message
    kb = InlineKeyboardBuilder()
    for i in range(0, len(PAYMENT_OPTIONS), 2):
        if i + 1 < len(PAYMENT_OPTIONS):
            kb.row(
                InlineKeyboardButton(
                    text=PAYMENT_OPTIONS[i]["text"],
                    callback_data=f"manualpay|amount|{PAYMENT_OPTIONS[i]['callback_data'].split('|')[1]}",
                ),
                InlineKeyboardButton(
                    text=PAYMENT_OPTIONS[i + 1]["text"],
                    callback_data=f"manualpay|amount|{PAYMENT_OPTIONS[i + 1]['callback_data'].split('|')[1]}",
                ),
            )
        else:
            kb.row(
                InlineKeyboardButton(
                    text=PAYMENT_OPTIONS[i]["text"],
                    callback_data=f"manualpay|amount|{PAYMENT_OPTIONS[i]['callback_data'].split('|')[1]}",
                )
            )
    kb.row(InlineKeyboardButton(text="Ввести сумму", callback_data="manualpay|amount|custom"))
    kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data="pay"))
    await edit_or_send_message(target_message=callback.message, text=CHOOSE_AMOUNT, reply_markup=kb.as_markup())

@router.callback_query(F.data == "manualpay|amount|custom")
async def manualpay_amount_custom(callback: CallbackQuery, state: FSMContext):
    from .texts import ENTER_AMOUNT, BTN_BACK
    from handlers.utils import edit_or_send_message
    await state.set_state(ManualPayStates.waiting_amount_input)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data="manualpay|start"))
    await edit_or_send_message(target_message=callback.message, text=ENTER_AMOUNT, reply_markup=kb.as_markup())

@router.message(ManualPayStates.waiting_amount_input)
async def manualpay_amount_input(message: Message, state: FSMContext):
    from .texts import INVALID_AMOUNT
    try:
        amount = int((message.text or "").strip())
        if amount < 10:
            raise ValueError
    except Exception:
        await message.answer(INVALID_AMOUNT)
        return
    await state.update_data(amount=amount)
    await _show_confirm(message, state)

@router.callback_query(F.data.startswith("manualpay|amount|"))
async def manualpay_amount_fixed(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("|")
    if parts[-1] == "custom":
        return await manualpay_amount_custom(callback, state)
    amount = int(parts[-1])
    await state.update_data(amount=amount)
    await _show_confirm(callback, state)

async def _show_confirm(event: CallbackQuery | Message, state: FSMContext):
    from .texts import CONFIRM_SUMMARY, BTN_CONFIRM, BTN_CANCEL, BTN_BACK
    from handlers.utils import edit_or_send_message
    data = await state.get_data()
    amount = data.get("amount")
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=BTN_CONFIRM, callback_data="manualpay|confirm"))
    kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data="manualpay|start"))
    kb.row(InlineKeyboardButton(text=BTN_CANCEL, callback_data="profile"))
    text = CONFIRM_SUMMARY.format(amount=amount, extra="")
    if isinstance(event, CallbackQuery):
        await edit_or_send_message(target_message=event.message, text=text, reply_markup=kb.as_markup())
    else:
        await event.answer(text, reply_markup=kb.as_markup())

@router.callback_query(F.data == "manualpay|confirm")
async def manualpay_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    from .texts import PAYMENT_DETAILS_TITLE, PAYMENT_DETAILS_CARD, PAYMENT_DETAILS_SBP, PAYMENT_DETAILS_REQUISITES, PAYMENT_DETAILS_LINK, BTN_I_PAID, BTN_CANCEL, BTN_OPEN_LINK
    from handlers.utils import edit_or_send_message
    method, details = _choose_details()
    data = await state.get_data()
    amount = data.get("amount")
    await state.update_data(method=method, details=details)

    if method == "multi":
        parts: list[str] = [PAYMENT_DETAILS_TITLE]
        link_url = None
        for kind, det in details:
            if kind == "card":
                parts.append(PAYMENT_DETAILS_CARD.format(card=det, amount=amount))
            elif kind == "sbp":
                parts.append(PAYMENT_DETAILS_SBP.format(phone=det.get("phone", ""), bank=det.get("bank", ""), amount=amount))
            elif kind == "link":
                parts.append(PAYMENT_DETAILS_LINK.format(amount=amount))
                if det:
                    parts.append(f"{det}")
                    link_url = det
            else:
                parts.append(PAYMENT_DETAILS_REQUISITES.format(requisites=det, amount=amount))
        text = "\n".join(parts)
        kb = InlineKeyboardBuilder()
        if link_url:
            from .texts import BTN_OPEN_LINK
            kb.row(InlineKeyboardButton(text=BTN_OPEN_LINK, url=link_url))
        kb.row(InlineKeyboardButton(text=BTN_I_PAID, callback_data="manualpay|send"))
        kb.row(InlineKeyboardButton(text=BTN_CANCEL, callback_data="profile"))
        await edit_or_send_message(target_message=callback.message, text=text, reply_markup=kb.as_markup())
        return
    elif method == "card":
        text = f"{PAYMENT_DETAILS_TITLE}\n" + PAYMENT_DETAILS_CARD.format(card=details, amount=amount)
    elif method == "sbp":
        text = f"{PAYMENT_DETAILS_TITLE}\n" + PAYMENT_DETAILS_SBP.format(
            phone=details.get("phone", ""),
            bank=details.get("bank", ""),
            amount=amount,
        )
    elif method == "link":
        text = f"{PAYMENT_DETAILS_TITLE}\n" + PAYMENT_DETAILS_LINK.format(amount=amount)
        if details:
            text += f"\n{details}"
    else:
        text = f"{PAYMENT_DETAILS_TITLE}\n" + PAYMENT_DETAILS_REQUISITES.format(requisites=details, amount=amount)

    kb = InlineKeyboardBuilder()
    if method == "link" and details:
        kb.row(InlineKeyboardButton(text=BTN_OPEN_LINK, url=details))
    kb.row(InlineKeyboardButton(text=BTN_I_PAID, callback_data="manualpay|send"))
    kb.row(InlineKeyboardButton(text=BTN_CANCEL, callback_data="profile"))
    await edit_or_send_message(target_message=callback.message, text=text, reply_markup=kb.as_markup())

@router.callback_query(F.data == "manualpay|send")
async def manualpay_send(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    from config import ADMIN_ID
    from .settings import TEXT_SENT_TO_ADMIN, TARGET, CHAT_ID, THREAD_ID, SIGN_KEY
    from .texts import ADMIN_NOTIFY_TITLE, ADMIN_USER_INFO, ADMIN_PAYMENT_INFO, ADMIN_BTNS_APPROVE, ADMIN_BTNS_REJECT
    from handlers.utils import edit_or_send_message

    data = await state.get_data()
    amount = data.get("amount")
    method = data.get("method")
    details = data.get("details")

    # Форматируем детали для админского уведомления
    if method == "sbp" and isinstance(details, dict):
        details_text = f"Номер: {details.get('phone', '')}, Банк: {details.get('bank', '')}"
    else:
        details_text = str(details)

    kb = InlineKeyboardBuilder()
    if TARGET == "topic":
        try:
            bot_user = await callback.bot.get_me()
            bot_username = bot_user.username
        except Exception:
            bot_username = ""
        approve_link = f"https://t.me/{bot_username}?start=manualpay_approve_{callback.from_user.id}_{amount}_{SIGN_KEY}"
        reject_link = f"https://t.me/{bot_username}?start=manualpay_reject_{callback.from_user.id}_{amount}_{SIGN_KEY}"
        kb.row(InlineKeyboardButton(text=ADMIN_BTNS_APPROVE, url=approve_link))
        kb.row(InlineKeyboardButton(text=ADMIN_BTNS_REJECT, url=reject_link))
    else:
        kb.row(InlineKeyboardButton(text=ADMIN_BTNS_APPROVE, callback_data=f"manualpay|approve|{callback.from_user.id}|{amount}"))
        kb.row(InlineKeyboardButton(text=ADMIN_BTNS_REJECT, callback_data=f"manualpay|reject|{callback.from_user.id}|{amount}"))
    
    text = (
        f"{ADMIN_NOTIFY_TITLE}\n"
        f"{ADMIN_USER_INFO.format(tg_id=callback.from_user.id, username=callback.from_user.username or '-')}\n"
        f"{ADMIN_PAYMENT_INFO.format(amount=amount, method=method, details=details_text)}"
    )

    try:
        if TARGET == "topic" and CHAT_ID:
            send_kwargs = {"chat_id": int(CHAT_ID), "text": text, "reply_markup": kb.as_markup()}
            if THREAD_ID is not None:
                send_kwargs["message_thread_id"] = int(THREAD_ID)
            await callback.bot.send_message(**send_kwargs)
        else:
            for admin_id in ADMIN_ID:
                try:
                    await callback.bot.send_message(admin_id, text=text, reply_markup=kb.as_markup())
                except Exception as e:
                    logger.error(f"[ManualPay] Ошибка отправки админу {admin_id}: {e}")
    except Exception as e:
        logger.error(f"[ManualPay] Ошибка отправки уведомления: {e}")

    await edit_or_send_message(target_message=callback.message, text=TEXT_SENT_TO_ADMIN, reply_markup=None)

@router.callback_query(F.data.startswith("manualpay|approve|"))
async def manualpay_approve(callback: CallbackQuery, session: AsyncSession):
    from database import update_balance
    from database.payments import add_payment, get_payment_by_user_amount
    from .texts import USER_APPROVED, BTN_GO_TO_BUY
    from handlers.utils import edit_or_send_message

    _, _, user_id_str, amount_str = callback.data.split("|")
    user_id = int(user_id_str)
    amount = float(amount_str)

    # Проверяем, не был ли платеж уже обработан
    existing_payment = await get_payment_by_user_amount(session, user_id, amount, "MANUAL")
    if existing_payment:
        await callback.answer("⚠️ Этот платеж уже был обработан ранее.", show_alert=True)
        # Обновляем сообщение, убирая кнопки
        old_text = callback.message.text or ""
        if "✅ Платёж подтверждён" not in old_text:
            new_text = f"{old_text}\n\n⚠️ Платёж уже был обработан ранее"
            await edit_or_send_message(target_message=callback.message, text=new_text, reply_markup=None)
        return

    await update_balance(session, user_id, amount)
    await add_payment(session, user_id, amount, payment_system="MANUAL")
    
    # Создаем клавиатуру с кнопкой для перехода к покупкам
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=BTN_GO_TO_BUY, callback_data="buy"))
    
    try:
        await callback.bot.send_message(user_id, USER_APPROVED.format(amount=int(amount)), reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer("✅ Зачислено", show_alert=True)
    old = callback.message.text or "Заявка на ручную оплату"
    new_text = f"{old}\n\n✅ Платёж подтверждён"
    # Убираем клавиатуру после обработки
    await edit_or_send_message(target_message=callback.message, text=new_text, reply_markup=None)

@router.callback_query(F.data.startswith("manualpay|reject|"))
async def manualpay_reject(callback: CallbackQuery, session: AsyncSession):
    from database.payments import get_payment_by_user_amount
    from .texts import USER_REJECTED
    from handlers.utils import edit_or_send_message
    _, _, user_id_str, amount_str = callback.data.split("|")
    user_id = int(user_id_str)
    amount = float(amount_str)

    # Проверяем, не был ли платеж уже обработан
    existing_payment = await get_payment_by_user_amount(session, user_id, amount, "MANUAL")
    if existing_payment:
        await callback.answer("⚠️ Этот платеж уже был обработан ранее.", show_alert=True)
        # Обновляем сообщение, убирая кнопки
        old_text = callback.message.text or ""
        if "❌ Платёж отклонён" not in old_text:
            new_text = f"{old_text}\n\n⚠️ Платёж уже был обработан ранее"
            await edit_or_send_message(target_message=callback.message, text=new_text, reply_markup=None)
        return

    try:
        await callback.bot.send_message(user_id, USER_REJECTED)
    except Exception:
        pass
    await callback.answer("❌ Отклонено", show_alert=True)
    old = callback.message.text or "Заявка на ручную оплату"
    new_text = f"{old}\n\n❌ Платёж отклонён"
    # Убираем клавиатуру после обработки
    await edit_or_send_message(target_message=callback.message, text=new_text, reply_markup=None)

from hooks.hooks import register_hook as _register_hook
@_register_hook("providers_config")
def providers_hook(providers: dict[str, dict], flags: dict[str, bool] | None = None) -> dict:
    return _providers_patch()
logger.info("[ManualPay] Модуль инициализирован — кнопка оплаты вручную подключена")

@register_hook("pay_menu_buttons")
async def pay_menu_buttons_hook(**kwargs):
    try:
        from .settings import ENABLE
        if not ENABLE:
            return None
        from .texts import BTN_MANUAL_PAY
        return [
            {"remove": "manualpay|start"},
            {"button": InlineKeyboardButton(text=BTN_MANUAL_PAY, callback_data="manualpay|start")},
        ]
    except Exception as e:
        logger.error(f"[ManualPay] Ошибка в pay_menu_buttons_hook: {e}")
        return None
# [file content end]