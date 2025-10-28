import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .settings import (
    ENABLE_DEVICES_COMMAND, ENABLE_DEVICES_BUTTON_IN_PROFILE, 
    ENABLE_DEVICES_BUTTON_IN_SUBSCRIPTION, DEVICES_BUTTON_PRIORITY,
    NOTIFICATION_SETTINGS_IN_MENU, DELETE_DEVICE_COOLDOWN_MINUTES
)
from .texts import (
    TITLE_DEVICES, NO_ACTIVE_SUBSCRIPTION, NO_DEVICES, DEVICES_COUNT,
    DEVICE_INFO, ERROR_NO_REMNAWAVE, ERROR_AUTH_FAILED, ERROR_GENERAL,
    BTN_BACK, BTN_BUY_SUBSCRIPTION, BTN_DELETE_DEVICE, TITLE_DELETE_SELECT,
    DELETE_SUCCESS, DELETE_FAIL, NO_DEVICES_TO_DELETE, TITLE_SELECT_SUBSCRIPTION,
    SUBSCRIPTION_INFO, BTN_DEVICES_PROFILE, BTN_DEVICES_SUBSCRIPTION, BTN_DEVICES_ADMIN, BTN_DEVICE_SETTINGS, TITLE_DEVICE_SETTINGS,
    DEVICE_NOTIFICATIONS_STATUS, BTN_TOGGLE_NOTIFICATIONS, NOTIFICATIONS_ENABLED,
    NOTIFICATIONS_DISABLED, NOTIFICATIONS_TOGGLE_SUCCESS, DELETE_COOLDOWN_ACTIVE, ERROR_ACCESS_DENIED,
    BTN_HWID_LIMIT_TOGGLE, HWID_LIMIT_TOGGLE_SUCCESS, HWID_LIMIT_ERROR
)
from logger import logger

router = Router(name="devices")


def format_time_remaining(minutes: int) -> str:
    """
    Форматирует время в читаемый формат:
    - Месяцы + дни (если >= 30 дней)
    - Недели + дни (если >= 7 дней)
    - Дни + часы (если >= 1 день)
    - Часы + минуты (если >= 1 час)
    - Минуты (если >= 1 минута)
    - Секунды (если < 1 минута)
    """
    if minutes <= 0:
        return "0 сек."
    
    seconds = minutes * 60
    
    # Месяцы (30 дней) + дни
    if minutes >= 43200:  # 30 дней
        months = minutes // 43200
        remaining_days = (minutes % 43200) // 1440
        if remaining_days > 0:
            return f"{months} мес. {remaining_days} д."
        return f"{months} мес."
    
    # Недели + дни
    if minutes >= 10080:  # 7 дней
        weeks = minutes // 10080
        remaining_days = (minutes % 10080) // 1440
        if remaining_days > 0:
            return f"{weeks} нед. {remaining_days} д."
        return f"{weeks} нед."
    
    # Дни + часы
    if minutes >= 1440:  # 1 день
        days = minutes // 1440
        remaining_hours = (minutes % 1440) // 60
        if remaining_hours > 0:
            return f"{days} д. {remaining_hours} ч."
        return f"{days} д."
    
    # Часы + минуты
    if minutes >= 60:
        hours = minutes // 60
        remaining_minutes = minutes % 60
        if remaining_minutes > 0:
            return f"{hours} ч. {remaining_minutes} мин."
        return f"{hours} ч."
    
    # Минуты
    if minutes >= 1:
        return f"{minutes} мин."
    
    # Секунды (если передано дробное значение минут)
    return f"{seconds} сек."


# Добавляем startup обработчик для router'а
@router.startup()
async def on_router_startup():
    """Обработчик startup события router'а для применения monkey patch"""
    logger.info("[devices] Router startup - применяем monkey patch...")
    success = apply_monkey_patch_delayed()
    if success:
        logger.info("[devices] Monkey patch успешно применен в router startup")
    else:
        logger.error("[devices] Не удалось применить monkey patch в router startup")


async def send_or_edit_message(callback: CallbackQuery, text: str, reply_markup=None):
    """Безопасная отправка или редактирование сообщения с обработкой разных типов контента"""
    try:
        # Пробуем отредактировать текст сообщения
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        # Если не получается отредактировать (например, сообщение с фото),
        # удаляем старое и отправляем новое
        try:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=reply_markup)
        except Exception as delete_error:
            # Если и удалить не получается, просто отправляем новое сообщение
            logger.warning(f"[devices] Не удалось удалить сообщение: {delete_error}")
            await callback.message.answer(text, reply_markup=reply_markup)


# Регистрируем хуки для добавления кнопки в разные меню
from hooks.hooks import register_hook

# Хук для меню профиля
if ENABLE_DEVICES_BUTTON_IN_PROFILE and (not ENABLE_DEVICES_BUTTON_IN_SUBSCRIPTION or DEVICES_BUTTON_PRIORITY == "profile"):
    async def profile_menu_hook(**kwargs):
        """Добавляет кнопку 'Устройства' в меню профиля только если есть активные подписки"""
        # Получаем chat_id из контекста (он равен tg_id)
        chat_id = kwargs.get('chat_id')
        session = kwargs.get('session')
        
        if not chat_id or not session:
            logger.warning(f"[devices] Не удалось получить chat_id ({chat_id}) или session для проверки подписок")
            return None
        
        try:
            # Проверяем активные подписки
            active_keys = await get_active_keys(session, chat_id)
            
            if not active_keys:
                logger.info(f"[devices] У пользователя {chat_id} нет активных подписок - кнопка не добавляется")
                return None
            
            logger.info(f"[devices] У пользователя {chat_id} есть {len(active_keys)} активных подписок - добавляем кнопку")
            return {
                "after": "balance", 
                "button": InlineKeyboardButton(text=BTN_DEVICES_PROFILE, callback_data="devices_profile")
            }
        except Exception as e:
            logger.error(f"[devices] Ошибка при проверке активных подписок для пользователя {chat_id}: {e}")
            return None
    
    register_hook("profile_menu", profile_menu_hook)
    logger.info("[devices] Хук для кнопки в профиле зарегистрирован")

# Хук для меню подписки
if ENABLE_DEVICES_BUTTON_IN_SUBSCRIPTION and (not ENABLE_DEVICES_BUTTON_IN_PROFILE or DEVICES_BUTTON_PRIORITY == "subscription"):
    async def subscription_menu_hook(**kwargs):
        """Добавляет кнопку 'Устройства' в меню подписки"""
        key_name = kwargs.get('key_name', '')
        return {
            "insert_at": 4,  # Вставляем на 5-ю позицию (после QR-кода, перед Личным кабинетом)
            "button": InlineKeyboardButton(text=BTN_DEVICES_SUBSCRIPTION, callback_data=f"devices_key|{key_name}")
        }
    
    register_hook("view_key_menu", subscription_menu_hook)  # Хук для меню просмотра ключа
    logger.info("[devices] Хук для кнопки в меню подписки зарегистрирован")

# Хук для админского меню редактирования ключей (оставляем как резерв)
async def admin_key_edit_hook(**kwargs):
    """Добавляет кнопку 'Устройства' в админское меню редактирования ключа"""
    key_details = kwargs.get('key_details', {})
    email = kwargs.get('email', '')
    
    if not key_details or not email:
        return None
    
    # Хук больше не нужен, используем monkey patch
    return None

register_hook("admin_key_edit", admin_key_edit_hook)
logger.info("[devices] Хук для кнопки в админском меню редактирования ключей зарегистрирован")

# Функция для отложенного применения monkey patch
def apply_monkey_patch_delayed():
    """Применяет monkey patch для добавления кнопки в админское меню"""
    try:
        logger.info("[devices] Применение отложенного monkey patch...")
        
        # Отложенный импорт для избежания циркулярных зависимостей
        import handlers.admin.users.keyboard
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        # Сохраняем оригинальную функцию
        original_build_key_edit_kb = handlers.admin.users.keyboard.build_key_edit_kb
        
        def patched_build_key_edit_kb(key_details: dict, email: str):
            """Патченная версия build_key_edit_kb с добавлением кнопки Устройства"""
            logger.info(f"[devices] ПАТЧЕННАЯ ФУНКЦИЯ ВЫЗВАНА! email={email}, key_details keys={list(key_details.keys()) if key_details else 'None'}")
            
            try:
                # Вызываем оригинальную функцию (она синхронная)
                markup = original_build_key_edit_kb(key_details, email)
                logger.info(f"[devices] Оригинальная функция выполнена, получена клавиатура с {len(markup.inline_keyboard)} рядами")
                
                # Получаем builder из markup
                builder = InlineKeyboardBuilder.from_markup(markup)
                
                # Проверяем, активна ли текущая подписка (простая проверка по данным ключа)
                try:
                    from datetime import datetime
                    
                    # Получаем данные из key_details
                    expiry_time = key_details.get('expiry_time', 0) if key_details else 0
                    is_frozen = key_details.get('is_frozen', False) if key_details else True
                    
                    # Проверяем, активна ли подписка
                    now_ms = datetime.utcnow().timestamp() * 1000
                    is_active = not is_frozen and expiry_time > now_ms
                    
                    should_show_button = is_active
                    logger.info(f"[devices] Ключ {email}: expiry_time={expiry_time}, is_frozen={is_frozen}, is_active={is_active}")
                
                except Exception as e:
                    logger.error(f"[devices] Ошибка при проверке активности подписки для {email}: {e}")
                    # В случае ошибки НЕ показываем кнопку (безопасный подход)
                    should_show_button = False
                
                # Добавляем кнопку устройства только если есть активные подписки
                if should_show_button:
                    # Создаем уникальный callback_data для этого email
                    import hashlib
                    import time
                    
                    # Создаем короткий хеш от email + текущего времени
                    hash_input = f"{email}_{int(time.time())}"
                    short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
                    
                    # Сохраняем в глобальном словаре для быстрого доступа
                    if not hasattr(patched_build_key_edit_kb, '_admin_contexts'):
                        patched_build_key_edit_kb._admin_contexts = {}
                        
                    patched_build_key_edit_kb._admin_contexts[short_hash] = email
                    
                    # Создаем кнопку устройства
                    device_button = InlineKeyboardButton(
                        text=BTN_DEVICES_ADMIN, 
                        callback_data=f"dev_adm_{short_hash}"
                    )
                    
                    # Получаем текущие кнопки из builder
                    current_markup = builder.as_markup()
                    buttons_list = current_markup.inline_keyboard
                    
                    # Вставляем кнопку устройства на 3-ю позицию (индекс 2)
                    if len(buttons_list) >= 3:
                        # Вставляем на 3-ю позицию
                        buttons_list.insert(2, [device_button])
                    else:
                        # Если меньше 3 кнопок, добавляем в конец
                        buttons_list.append([device_button])
                    
                    # Пересоздаем builder с новым порядком кнопок
                    builder = InlineKeyboardBuilder()
                    for row in buttons_list:
                        builder.row(*row)
                    
                    logger.info(f"[devices] Кнопка 'Устройства' вставлена на 3-ю позицию для пользователя {email}")
                else:
                    logger.info(f"[devices] Кнопка 'Устройства' НЕ добавлена - у пользователя {email} нет активных подписок")
                
                new_markup = builder.as_markup()
                logger.info(f"[devices] Добавлена кнопка Устройства! Итого рядов: {len(new_markup.inline_keyboard)} (было {len(markup.inline_keyboard)})")
                logger.info(f"[devices] Последняя кнопка: {new_markup.inline_keyboard[-1][0].text}")
                return new_markup
                
            except Exception as e:
                logger.error(f"[devices] Ошибка в патченной функции: {e}")
                # В случае ошибки возвращаем оригинальную клавиатуру
                return original_build_key_edit_kb(key_details, email)
        
        # Заменяем функцию в keyboard модуле
        handlers.admin.users.keyboard.build_key_edit_kb = patched_build_key_edit_kb
        logger.info("[devices] Monkey patch для build_key_edit_kb в keyboard модуле применен!")
        
        # Также нужно заменить в users_handler, так как функция импортирована напрямую
        import handlers.admin.users.users_handler
        handlers.admin.users.users_handler.build_key_edit_kb = patched_build_key_edit_kb
        logger.info("[devices] Monkey patch для build_key_edit_kb в users_handler модуле применен!")
        
        # Проверяем, что функция действительно заменена
        current_func = handlers.admin.users.keyboard.build_key_edit_kb
        logger.info(f"[devices] Текущая функция build_key_edit_kb: {current_func.__name__}")
        
        return True
        
    except Exception as e:
        logger.error(f"[devices] Ошибка при применении monkey patch: {e}")
        return False

# Monkey patch будет применен позже через router startup event


if ENABLE_DEVICES_COMMAND:
    logger.info("[devices] Модуль команды /devices инициализирован")

    @router.message(F.text == "/devices")
    async def handle_devices_command(message: Message, session: AsyncSession):
        """Обработчик команды /devices для показа HWID устройств пользователя"""
        tg_id = message.chat.id
        
        try:
            # Получаем активные подписки
            active_keys = await get_active_keys(session, tg_id)
            
            if not active_keys:
                # Если нет активной подписки - показываем сообщение с кнопкой покупки
                kb = InlineKeyboardBuilder()
                kb.row(InlineKeyboardButton(text=BTN_BUY_SUBSCRIPTION, callback_data="buy"))
                
                await message.answer(
                    f"{TITLE_DEVICES}\n\n{NO_ACTIVE_SUBSCRIPTION}",
                    reply_markup=kb.as_markup()
                )
                return
            
            # Если подписка одна - сразу показываем устройства
            if len(active_keys) == 1:
                await show_devices_for_key(message, session, active_keys[0])
                return
            
            # Если подписок несколько - показываем меню выбора
            await show_subscription_selection(message, session, active_keys)
            
        except Exception as e:
            logger.error(f"[devices] Ошибка в обработчике /devices для пользователя {tg_id}: {e}")
            await message.answer(f"{TITLE_DEVICES}\n\n{ERROR_GENERAL}")


    # Меню выбора устройства для удаления
    @router.callback_query(F.data.startswith("devices_delete_menu"))
    async def handle_delete_menu(callback: CallbackQuery, session: AsyncSession):
        tg_id = callback.message.chat.id
        
        try:
            # Парсим callback_data: devices_delete_menu|client_id или devices_delete_menu|hash_key
            parts = callback.data.split("|")
            admin_email = None
            client_id = None
            
            if len(parts) >= 2:
                second_part = parts[1]
                
                # Проверяем, является ли второй параметр хешем (8 символов)
                if len(second_part) == 8 and second_part.isalnum():
                    # Это хеш - получаем данные из контекста
                    delete_contexts = getattr(show_devices_for_key, '_delete_contexts', {})
                    if second_part in delete_contexts:
                        context = delete_contexts[second_part]
                        admin_email = context['admin_email']
                        client_id = context['client_id']
                    else:
                        await callback.answer("❌ Контекст устарел, попробуйте снова", show_alert=True)
                        return
                else:
                    # Это обычный client_id
                    client_id = second_part
            else:
                # Для обратной совместимости - берем первый активный ключ
                active_keys = await get_active_keys(session, tg_id)
                if not active_keys:
                    await send_or_edit_message(callback, NO_ACTIVE_SUBSCRIPTION, back_kb())
                    return
                client_id = active_keys[0].client_id
            
            # БЕЗОПАСНОСТЬ: Проверяем владение устройством (кроме админов)
            if not admin_email:
                if not await verify_device_ownership(session, tg_id, client_id):
                    logger.error(f"[devices] SECURITY ALERT: Попытка НСД! tg_id={tg_id} пытается удалить устройство client_id={client_id}")
                    await callback.answer(ERROR_ACCESS_DENIED, show_alert=True)
                    return
                
                # Проверяем кулдаун только для обычных пользователей (НЕ для админов)
                can_delete, remaining_minutes = await check_delete_cooldown(session, tg_id)
                if not can_delete:
                    time_str = format_time_remaining(remaining_minutes)
                    cooldown_message = DELETE_COOLDOWN_ACTIVE.format(time=time_str)
                    logger.info(f"[devices] Cooldown активен для tg_id={tg_id}, осталось {time_str}")
                    # Отправляем как обычное сообщение + alert для надежности
                    await callback.answer(cooldown_message, show_alert=True)
                    await callback.message.answer(cooldown_message)
                    return
            
            devices = await get_devices_for_client_id(session, client_id)
            if not devices:
                await send_or_edit_message(callback, NO_DEVICES_TO_DELETE, back_kb())
                return
                
            kb = InlineKeyboardBuilder()
            for idx, device in enumerate(devices):
                hwid = device.get("hwid")
                model = device.get("deviceModel") or hwid[:8] if hwid else "?"
                # Используем индекс вместо полного hwid для экономии места
                kb.row(InlineKeyboardButton(
                    text=f"🗑️ {model}", 
                    callback_data=f"dev_del|{idx}"
                ))
            
            # Кнопка "Назад" с учетом админского контекста
            if admin_email:
                # Создаем короткий хеш для кнопки назад
                import hashlib
                import time
                back_hash_input = f"back_{admin_email}_{int(time.time())}"
                back_hash = hashlib.md5(back_hash_input.encode()).hexdigest()[:8]
                
                # Сохраняем в глобальном контексте администратора
                from handlers.admin.users.keyboard import build_key_edit_kb
                if not hasattr(build_key_edit_kb, '_admin_contexts'):
                    build_key_edit_kb._admin_contexts = {}
                build_key_edit_kb._admin_contexts[back_hash] = admin_email
                
                back_callback = f"dev_adm_{back_hash}"
            else:
                back_callback = "devices_back"
            kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data=back_callback))
            
            # Сохраняем временно данные в контексте пользователя для удаления
            await store_delete_context(session, tg_id, client_id, devices, admin_email)
            
            await send_or_edit_message(
                callback,
                f"{TITLE_DEVICES}\n\n{TITLE_DELETE_SELECT}",
                kb.as_markup()
            )
        except Exception as e:
            logger.error(f"[devices] Ошибка в меню удаления для пользователя {tg_id}: {e}")
            await send_or_edit_message(callback, ERROR_GENERAL, back_kb())


    # Удаление выбранного устройства
    @router.callback_query(F.data.startswith("dev_del|"))
    async def handle_delete_device(callback: CallbackQuery, session: AsyncSession):
        tg_id = callback.message.chat.id
        
        try:
            # Парсим callback_data: dev_del|index
            device_index = int(callback.data.split("|")[1])
            
            # Получаем данные из контекста
            delete_context = await get_delete_context(session, tg_id)
            if not delete_context or device_index >= len(delete_context['devices']):
                await send_or_edit_message(callback, ERROR_GENERAL, back_kb())
                return
                
            client_id = delete_context['client_id']
            device = delete_context['devices'][device_index]
            hwid = device.get("hwid")
            
            # БЕЗОПАСНОСТЬ: Проверяем права доступа к устройству
            admin_email = delete_context.get('admin_email')
            
            if not admin_email:
                # Для обычных пользователей проверяем владение
                if not await verify_device_ownership(session, tg_id, client_id):
                    logger.error(f"[devices] SECURITY ALERT: НСД при удалении! tg_id={tg_id}, client_id={client_id}")
                    await callback.answer(ERROR_ACCESS_DENIED, show_alert=True)
                    return
                
                # Проверяем кулдаун
                can_delete, remaining_minutes = await check_delete_cooldown(session, tg_id)
                if not can_delete:
                    time_str = format_time_remaining(remaining_minutes)
                    await callback.answer(
                        DELETE_COOLDOWN_ACTIVE.format(time=time_str),
                        show_alert=True
                    )
                    return
            
            # Получаем серверы для поиска Remnawave
            from database.servers import get_servers
            from panels.remnawave import RemnawaveAPI
            from config import REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD
            
            servers = await get_servers(session=session)
            remna_server = None
            for cluster_servers in servers.values():
                for server in cluster_servers:
                    if server.get("panel_type", "") == "remnawave":
                        remna_server = server
                        break
                if remna_server:
                    break
                    
            if not remna_server:
                await send_or_edit_message(callback, ERROR_NO_REMNAWAVE, back_kb())
                return
                
            # Подключаемся к API и удаляем устройство
            api = RemnawaveAPI(remna_server["api_url"])
            if not await api.login(REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD):
                await send_or_edit_message(callback, ERROR_AUTH_FAILED, back_kb())
                return
                
            success = await api.delete_user_hwid_device(client_id, hwid)
            
            # Если устройство успешно удалено
            if success:
                # Обновляем timestamp последнего удаления (только для обычных пользователей)
                if not admin_email:
                    await update_delete_timestamp(session, tg_id)
                
                try:
                    from .monitor import device_monitor
                    if device_monitor:
                        logger.info(f"[devices] Запускаем немедленную проверку устройств после удаления для пользователя {tg_id}")
                        asyncio.create_task(device_monitor.trigger_immediate_check(tg_id))
                except Exception as e:
                    logger.error(f"[devices] Ошибка запуска немедленной проверки: {e}")
            
            # Проверяем админский контекст перед очисткой
            admin_email = delete_context.get('admin_email')
            
            # Очищаем контекст после удаления
            await clear_delete_context(session, tg_id)
            
            # Формируем кнопку возврата в зависимости от контекста
            kb = InlineKeyboardBuilder()
            if admin_email:
                # Создаем короткий хеш для кнопки назад после удаления
                import hashlib
                import time
                del_back_hash_input = f"del_back_{admin_email}_{int(time.time())}"
                del_back_hash = hashlib.md5(del_back_hash_input.encode()).hexdigest()[:8]
                
                # Сохраняем в глобальном контексте администратора
                from handlers.admin.users.keyboard import build_key_edit_kb
                if not hasattr(build_key_edit_kb, '_admin_contexts'):
                    build_key_edit_kb._admin_contexts = {}
                build_key_edit_kb._admin_contexts[del_back_hash] = admin_email
                
                kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data=f"dev_adm_{del_back_hash}"))
            else:
                kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data="devices_back"))
            
            if success:
                await send_or_edit_message(callback, DELETE_SUCCESS, kb.as_markup())
            else:
                await send_or_edit_message(callback, DELETE_FAIL, kb.as_markup())
                
        except Exception as e:
            logger.error(f"[devices] Ошибка при удалении устройства для пользователя {tg_id}: {e}")
            await send_or_edit_message(callback, ERROR_GENERAL, back_kb())


    # Обработчик выбора подписки
    @router.callback_query(F.data.startswith("devices_show|"))
    async def handle_show_subscription_devices(callback: CallbackQuery, session: AsyncSession):
        client_id = callback.data.split("|", 1)[1]
        
        try:
            # Находим ключ по client_id
            from database import get_keys
            tg_id = callback.message.chat.id
            keys = await get_keys(session, tg_id)
            selected_key = None
            
            for key in keys:
                if key.client_id == client_id:
                    selected_key = key
                    break
            
            if not selected_key:
                await send_or_edit_message(callback, ERROR_GENERAL, back_kb())
                return
            
            await show_devices_for_key(callback, session, selected_key, is_callback=True)
            
        except Exception as e:
            logger.error(f"[devices] Ошибка при выборе подписки {client_id}: {e}")
            await send_or_edit_message(callback, ERROR_GENERAL, back_kb())

    # Обработчик кнопки "Устройства" из профиля
    @router.callback_query(F.data == "devices_profile")
    async def handle_devices_from_profile(callback: CallbackQuery, session: AsyncSession):
        """Обработчик кнопки 'Устройства' из меню профиля"""
        await handle_devices_menu(callback, session, back_to="profile")

    # Обработчик кнопки "Устройства" из меню подписки
    @router.callback_query(F.data.startswith("devices_key|"))
    async def handle_devices_from_subscription(callback: CallbackQuery, session: AsyncSession):
        """Обработчик кнопки 'Устройства' из меню подписки"""
        tg_id = callback.message.chat.id
        
        try:
            # Извлекаем key_name из callback_data
            key_name = callback.data.split("|", 1)[1]
            
            # Получаем информацию о ключе по имени
            from database import get_keys
            keys = await get_keys(session, tg_id)
            
            # Ищем ключ с нужным именем (email)
            selected_key = None
            for key in keys:
                if key.email == key_name:
                    selected_key = key
                    break
            
            if not selected_key:
                await callback.answer("❌ Ключ не найден")
                return
            
            # Проверяем, что ключ активен
            from datetime import datetime
            now_ms = datetime.utcnow().timestamp() * 1000
            if selected_key.is_frozen or selected_key.expiry_time <= now_ms:
                await callback.answer("❌ Ключ не активен")
                return
            
            # Показываем устройства для этого ключа
            await show_devices_for_key(callback, session, selected_key, is_callback=True, back_to="keys")
            
        except Exception as e:
            logger.error(f"[devices] Ошибка в обработчике подписки для пользователя {tg_id}: {e}")
            await callback.answer("❌ Произошла ошибка")

    # Обработчик кнопки "Устройства" из админского меню редактирования ключа
    @router.callback_query(F.data.startswith("dev_adm_"))
    async def handle_devices_from_admin(callback: CallbackQuery, session: AsyncSession):
        """Обработчик кнопки 'Устройства' из админского меню редактирования ключа"""
        try:
            # Извлекаем hash из callback_data
            hash_key = callback.data.replace("dev_adm_", "")
            
            # Получаем email из сохраненного контекста
            # Импортируем функцию с контекстом
            from handlers.admin.users.keyboard import build_key_edit_kb
            admin_contexts = getattr(build_key_edit_kb, '_admin_contexts', {})
            
            if hash_key not in admin_contexts:
                await callback.answer("❌ Контекст устарел, попробуйте снова", show_alert=True)
                return
                
            email = admin_contexts[hash_key]
            logger.info(f"[devices] Админ запросил устройства для пользователя: {email} (hash: {hash_key})")
            
            if not email:
                await callback.answer("❌ Некорректные данные")
                return
            
            # Получаем информацию о ключе по email
            from database import get_key_details
            key_details = await get_key_details(session, email)
            
            if not key_details:
                await callback.answer("❌ Ключ не найден")
                return
            
            # Создаем объект ключа для совместимости с show_devices_for_key
            class AdminKeyWrapper:
                def __init__(self, key_details):
                    self.client_id = key_details.get('client_id')
                    self.email = key_details.get('email')
                    self.expiry_time = key_details.get('expiry_time')
                    self.is_frozen = key_details.get('is_frozen', False)
            
            admin_key = AdminKeyWrapper(key_details)
            
            # Показываем устройства для этого ключа с возвратом в админское меню
            await show_devices_for_key(callback, session, admin_key, is_callback=True, back_to="admin", admin_email=email)
            
        except Exception as e:
            logger.error(f"[devices] Ошибка в админском обработчике устройств: {e}")
            await callback.answer("❌ Произошла ошибка")

    async def handle_devices_menu(callback: CallbackQuery, session: AsyncSession, back_to: str = "profile"):
        """Общий обработчик меню устройств"""
        tg_id = callback.message.chat.id
        
        try:
            # Получаем активные подписки
            active_keys = await get_active_keys(session, tg_id)
            
            if not active_keys:
                # Если нет активной подписки - показываем сообщение с кнопкой покупки
                kb = InlineKeyboardBuilder()
                kb.row(InlineKeyboardButton(text=BTN_BUY_SUBSCRIPTION, callback_data="buy"))
                kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data=back_to))
                
                await send_or_edit_message(
                    callback,
                    f"{TITLE_DEVICES}\n\n{NO_ACTIVE_SUBSCRIPTION}",
                    kb.as_markup()
                )
                return
            
            # Если подписка одна - сразу показываем устройства
            if len(active_keys) == 1:
                await show_devices_for_key(callback, session, active_keys[0], is_callback=True, back_to=back_to)
                return
            
            # Если подписок несколько - показываем меню выбора
            await show_subscription_selection_callback(callback, session, active_keys, back_to=back_to)
            
        except Exception as e:
            logger.error(f"[devices] Ошибка в обработчике кнопки профиля для пользователя {tg_id}: {e}")
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data="profile"))
            await send_or_edit_message(callback, f"{TITLE_DEVICES}\n\n{ERROR_GENERAL}", kb.as_markup())

    # Кнопка назад из меню удаления
    @router.callback_query(F.data == "devices_back")
    async def handle_back(callback: CallbackQuery, session: AsyncSession):
        tg_id = callback.message.chat.id
        
        # Проверяем есть ли админский контекст перед очисткой
        delete_context = await get_delete_context(session, tg_id)
        admin_email = delete_context.get('admin_email') if delete_context else None
        
        # Очищаем контекст удаления
        await clear_delete_context(session, tg_id)
        
        # Если был админский контекст, возвращаемся в админское меню
        if admin_email:
            # Создаем короткий хеш для возврата в админское меню
            import hashlib
            import time
            admin_back_hash_input = f"admin_back_{admin_email}_{int(time.time())}"
            admin_back_hash = hashlib.md5(admin_back_hash_input.encode()).hexdigest()[:8]
            
            # Сохраняем в глобальном контексте администратора
            from handlers.admin.users.keyboard import build_key_edit_kb
            if not hasattr(build_key_edit_kb, '_admin_contexts'):
                build_key_edit_kb._admin_contexts = {}
            build_key_edit_kb._admin_contexts[admin_back_hash] = admin_email
            
            # Имитируем callback для админского меню
            callback.data = f"dev_adm_{admin_back_hash}"
            await handle_devices_from_admin(callback, session)
        else:
            # Возвращаемся к главному меню устройств через callback (по умолчанию в профиль)
            await handle_devices_menu(callback, session, back_to="profile")
        
    # Обработчик кнопки "Назад" в меню ключей  
    @router.callback_query(F.data == "keys")
    async def handle_back_to_keys(callback: CallbackQuery):
        """Возврат в меню ключей"""
        try:
            from handlers.keys.key_view import show_all_keys
            await show_all_keys(callback.message, callback.message.chat.id)
        except Exception as e:
            logger.error(f"[devices] Ошибка возврата в меню ключей: {e}")
            # Fallback - просто отвечаем пользователю
            await callback.answer("❌ Ошибка возврата. Используйте /profile или /keys")
            
    # Обработчик возврата к конкретному ключу
    @router.callback_query(F.data.startswith("key_view|"))
    async def handle_back_to_specific_key(callback: CallbackQuery, session: AsyncSession):
        """Возврат к конкретному ключу"""
        try:
            key_name = callback.data.split("|", 1)[1]
            from handlers.keys.key_view import render_key_info
            import os
            image_path = os.path.join("img", "pic_view.jpg")
            await render_key_info(callback.message, session, key_name, image_path)
        except Exception as e:
            logger.error(f"[devices] Ошибка возврата к ключу: {e}")
            # Fallback - просто отвечаем пользователю
            await callback.answer("❌ Ошибка возврата. Используйте /keys")
        
    # Обработчик настроек уведомлений об устройствах
    @router.callback_query(F.data == "device_settings")
    async def handle_device_settings(callback: CallbackQuery, session: AsyncSession):
        """Показывает настройки уведомлений об устройствах"""
        tg_id = callback.message.chat.id
        
        try:
            from .monitor import get_user_notification_setting
            
            # Получаем текущую настройку пользователя
            notifications_enabled = get_user_notification_setting(tg_id)
            status_text = NOTIFICATIONS_ENABLED if notifications_enabled else NOTIFICATIONS_DISABLED
            action_text = "Отключить" if notifications_enabled else "Включить"
            
            # Формируем текст настроек
            settings_text = f"{TITLE_DEVICE_SETTINGS}\n\n{DEVICE_NOTIFICATIONS_STATUS.format(status=status_text)}"
            
            # Создаем клавиатуру
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(
                text=BTN_TOGGLE_NOTIFICATIONS.format(action=action_text),
                callback_data="toggle_device_notifications"
            ))
            kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data="devices_profile"))
            
            await send_or_edit_message(callback, settings_text, kb.as_markup())
            
        except Exception as e:
            logger.error(f"[devices] Ошибка в настройках устройств для пользователя {tg_id}: {e}")
            await send_or_edit_message(callback, ERROR_GENERAL, back_kb())

    # Обработчик переключения уведомлений
    @router.callback_query(F.data == "toggle_device_notifications")
    async def handle_toggle_notifications(callback: CallbackQuery, session: AsyncSession):
        """Переключает настройку уведомлений об устройствах"""
        tg_id = callback.message.chat.id
        
        try:
            from .monitor import get_user_notification_setting, set_user_notification_setting
            
            # Получаем текущую настройку и переключаем ее
            current_setting = get_user_notification_setting(tg_id)
            new_setting = not current_setting
            
            # Сохраняем новую настройку
            set_user_notification_setting(tg_id, new_setting)
            
            # Показываем сообщение об успешном изменении
            await send_or_edit_message(callback, NOTIFICATIONS_TOGGLE_SUCCESS, back_kb())
            
            logger.info(f"[devices] Пользователь {tg_id} {'включил' if new_setting else 'отключил'} уведомления об устройствах")
            
        except Exception as e:
            logger.error(f"[devices] Ошибка переключения уведомлений для пользователя {tg_id}: {e}")
            await send_or_edit_message(callback, ERROR_GENERAL, back_kb())

    # Обработчик управления лимитом HWID (для админов в модуле devices)
    @router.callback_query(F.data.startswith("toggle_hwid_limit|"))
    async def handle_toggle_hwid_limit(callback: CallbackQuery, session: AsyncSession):
        """Переключает лимит HWID устройств для пользователя (только для админов)"""
        tg_id = callback.message.chat.id
        
        try:
            # Извлекаем client_id из callback_data
            client_id = callback.data.split("|", 1)[1]
            
            # Получаем информацию о ключе
            from database import get_key_details
            key_details = None
            
            # Находим email ключа по client_id
            from database.models import Key
            from sqlalchemy import select
            stmt = select(Key).where(Key.client_id == client_id)
            result = await session.execute(stmt)
            key = result.scalar_one_or_none()
            
            if not key:
                await callback.answer("❌ Ключ не найден", show_alert=True)
                return
            
            # Получаем Remnawave сервер
            from database.servers import get_servers
            from panels.remnawave import RemnawaveAPI
            from config import REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD
            
            servers = await get_servers(session=session)
            remna_server = None
            for cluster_servers in servers.values():
                for server in cluster_servers:
                    if server.get("panel_type", "") == "remnawave":
                        remna_server = server
                        break
                if remna_server:
                    break

            if not remna_server:
                await callback.answer("🚫 Нет доступного сервера Remnawave", show_alert=True)
                return

            # Получаем inbound_ids из всех Remnawave серверов кластера
            # (необходимо для update_user - API требует activeInternalSquads)
            inbound_ids = []
            cluster_id = key.cluster_id if hasattr(key, 'cluster_id') else None
            if cluster_id and cluster_id in servers:
                cluster_servers = servers[cluster_id]
                remnawave_servers = [s for s in cluster_servers if s.get("panel_type", "").lower() == "remnawave"]
                inbound_ids = [s["inbound_id"] for s in remnawave_servers if s.get("inbound_id")]
            
            if not inbound_ids:
                # Если не удалось получить из кластера, пробуем из текущего сервера
                if remna_server.get("inbound_id"):
                    inbound_ids = [remna_server["inbound_id"]]
            
            if not inbound_ids:
                await callback.answer("❌ Не удалось определить inbound_ids сервера", show_alert=True)
                return
            
            logger.info(f"[devices] Получены inbound_ids: {inbound_ids}")

            # Подключаемся к API
            api = RemnawaveAPI(remna_server["api_url"])
            if not await api.login(REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD):
                await callback.answer("❌ Ошибка авторизации в Remnawave", show_alert=True)
                return

            # Получаем информацию о HWID устройствах пользователя
            # API wrapper возвращает list устройств напрямую, не dict с {"response": ...}
            devices_list = await api.get_user_hwid_devices(client_id)
            logger.info(f"[devices] devices_list тип: {type(devices_list)}, количество: {len(devices_list) if devices_list else 0}")
            
            if devices_list is None:
                await callback.answer("❌ Не удалось получить информацию об устройствах", show_alert=True)
                return
            
            # Получаем лимит из тарифа
            from database.models import Tariff
            
            device_limit = 4   # Дефолтное значение
            
            # Безопасно получаем tariff_id (может быть обычный Key или AdminKeyWrapper)
            tariff_id = getattr(key, 'tariff_id', None)
            if tariff_id:
                stmt = select(Tariff).where(Tariff.id == tariff_id)
                result = await session.execute(stmt)
                tariff = result.scalar_one_or_none()
                if tariff and tariff.device_limit:
                    device_limit = tariff.device_limit
            
            # Получаем текущее количество устройств
            current_device_count = len(devices_list) if devices_list else 0
            
            logger.info(f"[devices] HWID Toggle: client_id={client_id}, устройств={current_device_count}, лимит_тарифа={device_limit}")
            
            # Простая логика toggle: используем TemporaryData для хранения последнего состояния
            # Получаем последнее сохраненное значение лимита из JSON data
            from database.models import TemporaryData
            stmt = select(TemporaryData).where(TemporaryData.tg_id == tg_id)
            result = await session.execute(stmt)
            temp_data = result.scalar_one_or_none()
            
            # Ключ в JSON data для хранения статуса HWID лимитов
            hwid_limits_key = 'hwid_limits'
            
            # Если есть сохраненное значение - инвертируем его
            # Если нет - смотрим по количеству устройств
            last_limit = None
            if temp_data and temp_data.data and isinstance(temp_data.data, dict):
                hwid_limits = temp_data.data.get(hwid_limits_key, {})
                if isinstance(hwid_limits, dict):
                    last_limit = hwid_limits.get(client_id)
            
            if last_limit is not None:
                try:
                    last_limit = int(last_limit)
                    if last_limit > 0:
                        # Был включен - отключаем
                        new_limit = 0
                        action_text = "отключён"
                    else:
                        # Был отключен - включаем
                        new_limit = device_limit
                        action_text = "включён"
                except (ValueError, TypeError):
                    # Если не можем распарсить - включаем лимит
                    new_limit = device_limit
                    action_text = "включён"
            else:
                # Нет сохраненного значения - смотрим по устройствам
                # Если устройств больше чем лимит - значит лимит отключен, включаем
                # Иначе - отключаем
                if current_device_count > device_limit:
                    new_limit = device_limit
                    action_text = "включён"
                else:
                    new_limit = 0
                    action_text = "отключён"
            
            logger.info(f"[devices] HWID Toggle: новый_лимит={new_limit}, действие={action_text}")
            
            # Получаем expiry_time из ключа для передачи в API
            # API требует expireAt в ISO формате
            from datetime import datetime, timezone
            expire_at_iso = None
            if hasattr(key, 'expiry_time') and key.expiry_time:
                # expiry_time может быть int (timestamp) или datetime
                if isinstance(key.expiry_time, int):
                    # Проверяем если timestamp в миллисекундах (больше чем 10^10)
                    timestamp = key.expiry_time
                    if timestamp > 10**10:
                        timestamp = timestamp / 1000  # Конвертируем из миллисекунд
                    # Конвертируем timestamp в datetime
                    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    expire_at_iso = dt.isoformat()
                elif hasattr(key.expiry_time, 'isoformat'):
                    # Это datetime объект
                    if key.expiry_time.tzinfo is None:
                        expire_at_iso = key.expiry_time.replace(tzinfo=timezone.utc).isoformat()
                    else:
                        expire_at_iso = key.expiry_time.isoformat()
                logger.info(f"[devices] expiry_time из БД: {key.expiry_time}, ISO: {expire_at_iso}")
            
            # Обновляем пользователя через API Remnawave
            # Python API использует snake_case (hwid_device_limit), не camelCase
            try:
                logger.info(f"[devices] Вызов api.update_user(uuid={client_id}, hwid_device_limit={new_limit}, expire_at={expire_at_iso}, inbound_ids={inbound_ids})")
                
                # Формируем параметры
                update_params = {
                    'uuid': client_id,
                    'hwid_device_limit': new_limit,
                    'active_user_inbounds': inbound_ids  # Обязательно передаем inbound_ids
                }
                
                # Добавляем expire_at только если есть
                if expire_at_iso:
                    update_params['expire_at'] = expire_at_iso
                
                success = await api.update_user(**update_params)
                logger.info(f"[devices] api.update_user вернул: {success}")
            except Exception as update_error:
                logger.error(f"[devices] Ошибка вызова update_user: {update_error}", exc_info=True)
                await callback.answer(HWID_LIMIT_ERROR, show_alert=True)
                return
            
            if success:
                # Сохраняем новое значение лимита в TemporaryData
                from database.models import TemporaryData
                stmt = select(TemporaryData).where(TemporaryData.tg_id == tg_id)
                result = await session.execute(stmt)
                temp_data = result.scalar_one_or_none()
                
                hwid_limits_key = 'hwid_limits'
                
                if temp_data:
                    # Обновляем существующую запись
                    if not temp_data.data or not isinstance(temp_data.data, dict):
                        temp_data.data = {}
                    if hwid_limits_key not in temp_data.data:
                        temp_data.data[hwid_limits_key] = {}
                    temp_data.data[hwid_limits_key][client_id] = new_limit
                    # Важно: помечаем как измененную для SQLAlchemy
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(temp_data, 'data')
                else:
                    # Создаем новую запись
                    temp_data = TemporaryData(
                        tg_id=tg_id,
                        data={hwid_limits_key: {client_id: new_limit}}
                    )
                    session.add(temp_data)
                await session.commit()
                
                # Показываем текущий статус лимита
                limit_status = f"✅ HWID лимит {action_text}"
                if new_limit > 0:
                    limit_status += f"\n📊 Лимит устройств: {new_limit}"
                else:
                    limit_status += f"\n♾️ Без лимита устройств"
                
                await callback.answer(limit_status, show_alert=True)
                logger.info(f"[devices] Админ {tg_id} изменил HWID лимит для {client_id}: {action_text} (новый лимит: {new_limit})")
                
                # Обновляем сообщение с устройствами, чтобы показать новый статус
                # Получаем ключ для обновления
                from database.models import Key as KeyModel
                stmt = select(KeyModel).where(KeyModel.client_id == client_id)
                result = await session.execute(stmt)
                updated_key = result.scalar_one_or_none()
                
                if updated_key:
                    # Используем email ключа как admin_email для show_devices_for_key
                    await show_devices_for_key(callback, session, updated_key, is_callback=True, back_to="admin", admin_email=key.email)
            else:
                await callback.answer(HWID_LIMIT_ERROR, show_alert=True)
                
        except Exception as e:
            logger.error(f"[devices] Ошибка переключения HWID лимита: {e}")
            await callback.answer(HWID_LIMIT_ERROR, show_alert=True)



# Вспомогательная функция для клавиатуры назад
def back_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data="profile"))
    return kb.as_markup()


async def get_active_keys(session: AsyncSession, tg_id: int):
    """Получает все активные ключи пользователя"""
    from database import get_keys
    
    keys = await get_keys(session, tg_id)
    now_ms = datetime.utcnow().timestamp() * 1000
    active_keys = [k for k in keys if not k.is_frozen and k.expiry_time > now_ms]
    
    return active_keys


async def show_subscription_selection(message: Message, session: AsyncSession, active_keys):
    """Показывает меню выбора подписки"""
    kb = InlineKeyboardBuilder()
    
    for key in active_keys:
        # Форматируем дату истечения
        expiry_date = datetime.utcfromtimestamp(key.expiry_time / 1000).strftime("%d.%m.%Y %H:%M")
        button_text = f"🔑 {key.email[:20]}..." if len(key.email) > 20 else f"🔑 {key.email}"
        
        kb.row(InlineKeyboardButton(
            text=button_text, 
            callback_data=f"devices_show|{key.client_id}"
        ))
    
    kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data="profile"))
    
    await message.answer(
        f"{TITLE_DEVICES}\n\n{TITLE_SELECT_SUBSCRIPTION}",
        reply_markup=kb.as_markup()
    )


async def show_subscription_selection_callback(callback: CallbackQuery, session: AsyncSession, active_keys, back_to="profile"):
    """Показывает меню выбора подписки для callback"""
    kb = InlineKeyboardBuilder()
    
    for key in active_keys:
        # Форматируем дату истечения
        expiry_date = datetime.utcfromtimestamp(key.expiry_time / 1000).strftime("%d.%m.%Y %H:%M")
        button_text = f"🔑 {key.email[:20]}..." if len(key.email) > 20 else f"🔑 {key.email}"
        
        kb.row(InlineKeyboardButton(
            text=button_text, 
            callback_data=f"devices_show|{key.client_id}"
        ))
    
    kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data=back_to))
    
    await send_or_edit_message(
        callback,
        f"{TITLE_DEVICES}\n\n{TITLE_SELECT_SUBSCRIPTION}",
        kb.as_markup()
    )


async def show_devices_for_key(message_or_callback, session: AsyncSession, key, is_callback=False, back_to="profile", admin_email=None):
    """Показывает устройства для конкретной подписки"""
    try:
        devices_data = await get_devices_for_client_id(session, key.client_id)
        
        # Получаем информацию о лимите устройств для админов через API
        hwid_limit_info = ""
        if admin_email:
            # Безопасно получаем tariff_id (может быть обычный Key или AdminKeyWrapper)
            tariff_id = getattr(key, 'tariff_id', None)
            if tariff_id:
                from database.models import Tariff
                from database.servers import get_servers
                from panels.remnawave import RemnawaveAPI
                from config import REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD
                
                # Получаем лимит из тарифа
                stmt = select(Tariff).where(Tariff.id == tariff_id)
                result = await session.execute(stmt)
                tariff = result.scalar_one_or_none()
                if tariff and tariff.device_limit:
                    device_limit = tariff.device_limit
                    
                    # Подключаемся к API для проверки реального статуса
                    servers = await get_servers(session=session)
                    remna_server = None
                    for cluster_servers in servers.values():
                        for server in cluster_servers:
                            if server.get("panel_type", "") == "remnawave":
                                remna_server = server
                                break
                        if remna_server:
                            break
                    
                    if remna_server:
                        try:
                            # Получаем сохраненное значение лимита из TemporaryData
                            from database.models import TemporaryData
                            # Определяем tg_id в зависимости от типа message_or_callback
                            if is_callback:
                                tg_id_for_check = message_or_callback.message.chat.id
                            else:
                                tg_id_for_check = message_or_callback.chat.id
                            
                            stmt_temp = select(TemporaryData).where(TemporaryData.tg_id == tg_id_for_check)
                            result_temp = await session.execute(stmt_temp)
                            temp_data = result_temp.scalar_one_or_none()
                            
                            current_limit = None
                            hwid_limits_key = 'hwid_limits'
                            if temp_data and temp_data.data and isinstance(temp_data.data, dict):
                                hwid_limits = temp_data.data.get(hwid_limits_key, {})
                                if isinstance(hwid_limits, dict):
                                    current_limit = hwid_limits.get(key.client_id)
                            
                            if current_limit is not None:
                                try:
                                    current_limit = int(current_limit)
                                except (ValueError, TypeError):
                                    current_limit = None
                            
                            # Получаем количество устройств
                            api = RemnawaveAPI(remna_server["api_url"])
                            if await api.login(REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD):
                                # Получаем HWID devices через API
                                api_devices_list = await api.get_user_hwid_devices(key.client_id)
                                if api_devices_list is not None:
                                    actual_count = len(api_devices_list) if api_devices_list else 0
                                    
                                    # Статус определяется по сохраненному значению
                                    if current_limit is not None and current_limit > 0:
                                        hwid_limit_info = f"\n\n📊 HWID лимит: ✅ Включен ({actual_count}/{current_limit})"
                                    else:
                                        hwid_limit_info = f"\n\n♾️ HWID лимит: ❌ Отключен ({actual_count} устройств)"
                        except Exception as api_error:
                            logger.error(f"[devices] Ошибка получения статуса HWID через API: {api_error}")
                            # Фоллбек на простой подсчет
                            current_device_count = len(devices_data) if devices_data else 0
                            hwid_limit_info = f"\n\n📊 HWID лимит: {current_device_count} устройств"
        
        # Формируем текст
        if not devices_data:
            text = f"{TITLE_DEVICES}\n\n🔑 {key.email}{hwid_limit_info}\n\n{NO_DEVICES}"
        else:
            text = f"{TITLE_DEVICES}\n\n🔑 {key.email}{hwid_limit_info}\n\n{DEVICES_COUNT.format(count=len(devices_data))}\n\n"
            for idx, device in enumerate(devices_data, 1):
                created = device.get("createdAt", "")[:19].replace("T", " ")
                updated = device.get("updatedAt", "")[:19].replace("T", " ")
                
                text += DEVICE_INFO.format(
                    idx=idx,
                    device_model=device.get('deviceModel') or '—',
                    platform=f"{device.get('platform') or '—'} / {device.get('osVersion') or '—'}",
                    user_agent=device.get('userAgent') or '—',
                    created_at=created,
                    updated_at=updated
                )
        
        # Добавляем кнопки
        kb = InlineKeyboardBuilder()
        if devices_data:
            # Для админского контекста создаем короткий хеш вместо передачи email напрямую
            if admin_email:
                import hashlib
                import time
                hash_input = f"del_{admin_email}_{key.client_id}_{int(time.time())}"
                short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
                
                # Сохраняем контекст для кнопки удаления
                if not hasattr(show_devices_for_key, '_delete_contexts'):
                    show_devices_for_key._delete_contexts = {}
                show_devices_for_key._delete_contexts[short_hash] = {
                    'admin_email': admin_email,
                    'client_id': key.client_id
                }
                
                delete_callback = f"devices_delete_menu|{short_hash}"
            else:
                delete_callback = f"devices_delete_menu|{key.client_id}"
                
            kb.row(InlineKeyboardButton(
                text=BTN_DELETE_DEVICE, 
                callback_data=delete_callback
            ))
        
        # Добавляем кнопку настроек уведомлений только для пользователей (не для админов)
        if NOTIFICATION_SETTINGS_IN_MENU and not admin_email:
            kb.row(InlineKeyboardButton(text=BTN_DEVICE_SETTINGS, callback_data="device_settings"))
        
        # Добавляем кнопку управления HWID лимитом для админов
        if admin_email:
            kb.row(InlineKeyboardButton(text=BTN_HWID_LIMIT_TOGGLE, callback_data=f"toggle_hwid_limit|{key.client_id}"))
        
        # Определяем куда возвращаться
        if back_to == "admin" and admin_email:
            # Если пришли из админского меню редактирования ключа, возвращаемся к нему
            from handlers.admin.users.keyboard import AdminUserEditorCallback
            # Получаем tg_id пользователя ключа из базы данных
            from database import get_key_details
            key_info = await get_key_details(session, admin_email)
            user_tg_id = key_info.get('tg_id', 0) if key_info else 0
            back_callback = AdminUserEditorCallback(action="users_key_edit", tg_id=user_tg_id, data=admin_email).pack()
        elif back_to == "keys" and is_callback:
            # Если пришли из меню конкретного ключа, возвращаемся к нему
            back_callback = f"key_view|{key.email}"
        else:
            back_callback = back_to if is_callback else "devices_back"
        kb.row(InlineKeyboardButton(text=BTN_BACK, callback_data=back_callback))
        
        # Отправляем или редактируем сообщение
        if is_callback:
            await send_or_edit_message(message_or_callback, text, kb.as_markup())
        else:
            await message_or_callback.answer(text, reply_markup=kb.as_markup())
            
    except Exception as e:
        logger.error(f"[devices] Ошибка при показе устройств для ключа {key.client_id}: {e}")
        error_text = f"{TITLE_DEVICES}\n\n{ERROR_GENERAL}"
        if is_callback:
            await send_or_edit_message(message_or_callback, error_text, back_kb())
        else:
            await message_or_callback.answer(error_text, reply_markup=back_kb())


async def get_devices_for_client_id(session: AsyncSession, client_id: str):
    """Получает устройства для конкретного client_id"""
    try:
        from database.servers import get_servers
        from panels.remnawave import RemnawaveAPI
        from config import REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD
        
        # Получаем серверы для поиска Remnawave
        servers = await get_servers(session=session)
        remna_server = None
        for cluster_servers in servers.values():
            for server in cluster_servers:
                if server.get("panel_type", "") == "remnawave":
                    remna_server = server
                    break
            if remna_server:
                break
        
        if not remna_server:
            logger.warning("[devices] Нет доступного сервера Remnawave")
            return []
        
        # Подключаемся к API
        api = RemnawaveAPI(remna_server["api_url"])
        if not await api.login(REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD):
            logger.error("[devices] Ошибка авторизации в Remnawave")
            return []
        
        # Получаем устройства
        devices = await api.get_user_hwid_devices(client_id)
        return devices or []
        
    except Exception as e:
        logger.error(f"[devices] Ошибка при получении устройств для client_id {client_id}: {e}")
        return []


async def store_delete_context(session: AsyncSession, tg_id: int, client_id: str, devices: list, admin_email: str = None):
    """Сохраняет контекст удаления во временную таблицу"""
    try:
        from database.temporary_data import create_temporary_data
        context_data = {
            'client_id': client_id,
            'devices': devices,
            'timestamp': datetime.utcnow().timestamp(),
            'admin_email': admin_email  # Сохраняем админский контекст
        }
        await create_temporary_data(session, tg_id, 'devices_delete_context', context_data)
    except Exception as e:
        logger.error(f"[devices] Ошибка при сохранении контекста удаления: {e}")


async def get_delete_context(session: AsyncSession, tg_id: int):
    """Получает контекст удаления из временной таблицы"""
    try:
        from database.temporary_data import get_temporary_data
        temp_data = await get_temporary_data(session, tg_id)
        
        if not temp_data or temp_data.get('state') != 'devices_delete_context':
            return None
        
        context = temp_data.get('data', {})
        
        # Проверяем, что данные не слишком старые (5 минут)
        if datetime.utcnow().timestamp() - context.get('timestamp', 0) > 300:
            await clear_delete_context(session, tg_id)
            return None
            
        return context
    except Exception as e:
        logger.error(f"[devices] Ошибка при получении контекста удаления: {e}")
        return None


async def clear_delete_context(session: AsyncSession, tg_id: int):
    """Очищает контекст удаления, но сохраняет метку времени кулдауна"""
    try:
        from database.temporary_data import get_temporary_data, create_temporary_data, clear_temporary_data
        
        # Сохраняем метку времени кулдауна если она есть
        temp_data = await get_temporary_data(session, tg_id)
        cooldown_timestamp = None
        
        if temp_data and temp_data.get('state') == 'last_device_delete':
            cooldown_timestamp = temp_data.get('data', {}).get('timestamp')
        
        # Очищаем все временные данные
        await clear_temporary_data(session, tg_id)
        
        # Восстанавливаем метку времени кулдауна
        if cooldown_timestamp is not None:
            await create_temporary_data(
                session,
                tg_id,
                'last_device_delete',
                {'timestamp': cooldown_timestamp}
            )
    except Exception as e:
        logger.error(f"[devices] Ошибка при очистке контекста удаления: {e}")


async def verify_device_ownership(session: AsyncSession, tg_id: int, client_id: str) -> bool:
    """
    Проверяет, принадлежит ли client_id данному пользователю.
    КРИТИЧНО для безопасности - предотвращает НСД (несанкционированный доступ).
    """
    try:
        from database import get_keys
        user_keys = await get_keys(session, tg_id)
        
        # Проверяем, есть ли client_id среди ключей пользователя
        for key in user_keys:
            if key.client_id == client_id:
                return True
        
        logger.warning(f"[devices] SECURITY: Попытка доступа к чужому client_id! tg_id={tg_id}, client_id={client_id}")
        return False
    except Exception as e:
        logger.error(f"[devices] Ошибка проверки владения устройством: {e}")
        return False


async def check_delete_cooldown(session: AsyncSession, tg_id: int) -> tuple[bool, int]:
    """
    Проверяет, прошёл ли кулдаун с последнего удаления устройства.
    Возвращает (can_delete: bool, remaining_minutes: int)
    """
    if DELETE_DEVICE_COOLDOWN_MINUTES <= 0:
        logger.debug(f"[devices] Кулдаун отключен (настройка = {DELETE_DEVICE_COOLDOWN_MINUTES})")
        return True, 0
    
    try:
        from database.temporary_data import get_temporary_data
        from datetime import datetime
        
        temp_data = await get_temporary_data(session, tg_id)
        
        # Проверяем последнее время удаления
        if temp_data and temp_data.get('state') == 'last_device_delete':
            last_delete_time = temp_data.get('data', {}).get('timestamp', 0)
            current_time = datetime.utcnow().timestamp()
            time_passed_minutes = (current_time - last_delete_time) / 60
            
            logger.info(f"[devices] Кулдаун для {tg_id}: прошло {time_passed_minutes:.2f} мин, требуется {DELETE_DEVICE_COOLDOWN_MINUTES} мин")
            
            if time_passed_minutes < DELETE_DEVICE_COOLDOWN_MINUTES:
                remaining_minutes = int(DELETE_DEVICE_COOLDOWN_MINUTES - time_passed_minutes) + 1
                logger.info(f"[devices] Кулдаун активен для {tg_id}, осталось {remaining_minutes} мин")
                return False, remaining_minutes
        
        logger.info(f"[devices] Кулдаун пройден для {tg_id}, удаление разрешено")
        return True, 0
    except Exception as e:
        logger.error(f"[devices] Ошибка при проверке кулдауна: {e}")
        return True, 0  # В случае ошибки разрешаем удаление


async def update_delete_timestamp(session: AsyncSession, tg_id: int):
    """Обновляет время последнего удаления устройства"""
    try:
        from database.temporary_data import create_temporary_data
        from datetime import datetime
        
        timestamp = datetime.utcnow().timestamp()
        await create_temporary_data(
            session, 
            tg_id, 
            'last_device_delete', 
            {'timestamp': timestamp}
        )
        logger.info(f"[devices] Обновлена метка времени удаления для {tg_id}: {timestamp}")
    except Exception as e:
        logger.error(f"[devices] Ошибка при обновлении времени удаления: {e}")



async def check_user_subscription_and_devices(session: AsyncSession, tg_id: int) -> tuple[bool, list]:
    """
    Проверяет наличие активной подписки и получает HWID устройства пользователя
    Возвращает: (has_active_subscription: bool, devices_data: list)
    """
    try:
        # Импортируем функции из database
        from database import get_keys
        from database.servers import get_servers
        
        # Получаем ключи пользователя
        keys = await get_keys(session, tg_id)
        
        # Проверяем активные ключи
        now_ms = datetime.utcnow().timestamp() * 1000
        active_keys = [k for k in keys if not k.is_frozen and k.expiry_time > now_ms]
        
        if not active_keys:
            return False, []
        
        # Берем первый активный ключ для получения устройств
        first_key = active_keys[0]
        
        # Получаем серверы для поиска Remnawave
        servers = await get_servers(session=session)
        remna_server = None
        for cluster_servers in servers.values():
            for server in cluster_servers:
                if server.get("panel_type", "") == "remnawave":
                    remna_server = server
                    break
            if remna_server:
                break
        
        if not remna_server:
            logger.warning("[devices] Нет доступного сервера Remnawave")
            return True, []
        
        # Импортируем API и конфиг
        from panels.remnawave import RemnawaveAPI
        from config import REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD
        
        # Подключаемся к API
        api = RemnawaveAPI(remna_server["api_url"])
        if not await api.login(REMNAWAVE_LOGIN, REMNAWAVE_PASSWORD):
            logger.error("[devices] Ошибка авторизации в Remnawave")
            return True, []
        
        # Получаем устройства
        devices = await api.get_user_hwid_devices(first_key.client_id)
        return True, devices or []
        
    except Exception as e:
        logger.error(f"[devices] Ошибка при проверке подписки и получении устройств: {e}")
        return False, []


# Импортируем глобальный объект монитора устройств
from .monitor import device_monitor

# API endpoint для оптимизированной проверки устройств
@router.callback_query(F.data == "trigger_device_check")
async def trigger_manual_device_check(callback: CallbackQuery):
    """Ручной триггер проверки устройств для админов"""
    try:
        if device_monitor and callback.from_user.id in [979417469]:  # Только для админов
            device_monitor.add_user_to_pending_check(callback.from_user.id)
            await callback.answer("✅ Проверка устройств запущена")
            logger.info(f"[devices] Ручной триггер проверки от админа {callback.from_user.id}")
        else:
            await callback.answer("❌ Нет доступа")
    except Exception as e:
        logger.error(f"[devices] Ошибка ручного триггера: {e}")
        await callback.answer("❌ Ошибка")

# Функция для внешнего использования - добавление пользователя в очередь проверки
def trigger_user_device_check(tg_id: int):
    """Внешняя функция для добавления пользователя в очередь проверки"""
    if device_monitor:
        device_monitor.add_user_to_pending_check(tg_id)
        logger.info(f"[devices] Внешний триггер: пользователь {tg_id} добавлен в очередь")
        return True
    logger.warning("[devices] Монитор устройств не инициализирован")
    return False


# Функция для modules_loader - регистрация HTTP webhook
def get_webhook_data():
    """
    Возвращает данные для регистрации HTTP webhook в modules_loader
    """
    from .settings import USE_HTTP_WEBHOOK, WEBHOOK_PATH
    
    if USE_HTTP_WEBHOOK:
        # Создаем специальный обработчик для HWID webhook /devices/webhook
        async def main_webhook_handler(request):
            """Обработчик HWID webhook для уведомлений от Remnawave"""
            try:
                logger.info(f"[devices] � WEBHOOK ВЫЗВАН! Путь: {request.path}")
                logger.info(f"[devices] �📨 ПОЛУЧЕН WEBHOOK ЗАПРОС на {WEBHOOK_PATH}")
                logger.info(f"[devices] 🌐 URL запроса: {request.url}")
                logger.info(f"[devices] 📋 Заголовки: {dict(request.headers)}")
                
                # Получаем JSON из запроса
                data = await request.json()
                logger.info(f"[devices] 📄 Данные webhook: {data}")
                
                # Проверяем, является ли это HWID уведомлением
                if data.get('type') == 'hwid_device_connected':
                    logger.info(f"[devices] 🚨 Получено HWID уведомление: {data.get('hwid')} для {data.get('user_uuid')}")
                    
                    # Импортируем и вызываем обработчик
                    from .http_webhook import handle_hwid_webhook
                    from .launcher import get_bot_instance
                    
                    bot = get_bot_instance()
                    if bot:
                        logger.info(f"[devices] 🤖 Bot instance найден: {bot}")
                        await handle_hwid_webhook(data, bot)
                        logger.info(f"[devices] ✅ HWID webhook обработан успешно")
                        
                        from aiohttp.web import json_response
                        return json_response({"status": "success", "message": "HWID notification processed"})
                    else:
                        logger.error("[devices] ❌ Bot instance не найден")
                        from aiohttp.web import json_response
                        return json_response({"status": "error", "message": "Bot not available"}, status=500)
                else:
                    logger.info(f"[devices] ⏩ Это не HWID уведомление, тип: {data.get('type', 'unknown')}")
                    from aiohttp.web import json_response
                    return json_response({"status": "ignored", "message": "Not HWID notification"})
                    
            except Exception as e:
                logger.error(f"[devices] ❌ Ошибка обработки основного webhook: {e}", exc_info=True)
                from aiohttp.web import json_response
                return json_response({"status": "error", "message": str(e)}, status=500)
        
        return {
            "path": WEBHOOK_PATH,  # "/devices/webhook"
            "handler": main_webhook_handler
        }
    return None