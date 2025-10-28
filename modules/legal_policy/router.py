"""
Модуль добавления кнопок пользовательского соглашения и политики конфиденциальности
в раздел "О сервисе" основного бота
Работает через перехват callback "about_vpn" без изменения основного кода
"""

import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from logger import logger

# Импортируем конфиг с обработкой ошибок
try:
    from .config import LegalPolicyConfig
    logger.info("[LegalPolicy] Конфиг импортирован успешно")
except Exception as e:
    logger.error(f"[LegalPolicy] Ошибка импорта конфига: {e}")
    
    # Fallback конфиг
    class LegalPolicyConfig:
        ENABLED = True
        TERMS_OF_SERVICE_URL = "https://telegra.ph/1-Pravila-ispolzovaniya-servisa-AXIOME-VPN-BOT-02-04"
        PRIVACY_POLICY_URL = "https://telegra.ph/1-Pravila-ispolzovaniya-servisa-AXIOME-VPN-BOT-02-04"
        TERMS_BUTTON_TEXT = "📄 Пользовательское соглашение"
        PRIVACY_BUTTON_TEXT = "🔒 Политика конфиденциальности"
        USE_WEBAPP_BUTTONS = False
        BUTTONS_POSITION = "bottom"
        BUTTONS_INLINE = True
        TERMS_WEBAPP_URL = "https://telegra.ph/1-Pravila-ispolzovaniya-servisa-AXIOME-VPN-BOT-02-04"
        PRIVACY_WEBAPP_URL = "https://telegra.ph/1-Pravila-ispolzovaniya-servisa-AXIOME-VPN-BOT-02-04"

router = Router()

# Глобальные переменные для кеширования импортов
_imports_cached = False
_import_cache = {}

def _lazy_import():
    """Ленивый импорт компонентов бота для избежания циклических импортов"""
    global _imports_cached, _import_cache
    
    if _imports_cached:
        return _import_cache
    
    try:
        from database.users import get_trial
        from handlers.utils import edit_or_send_message
        from handlers.texts import get_about_vpn
        from config import (
            DONATIONS_ENABLE,
            SUPPORT_CHAT_URL, 
            CHANNEL_EXISTS,
            CHANNEL_URL,
            SHOW_START_MENU_ONCE
        )
        from handlers.buttons import SUPPORT, CHANNEL, BACK
        
        _import_cache = {
            'get_trial': get_trial,
            'edit_or_send_message': edit_or_send_message,
            'get_about_vpn': get_about_vpn,
            'DONATIONS_ENABLE': DONATIONS_ENABLE,
            'SUPPORT_CHAT_URL': SUPPORT_CHAT_URL,
            'CHANNEL_EXISTS': CHANNEL_EXISTS,
            'CHANNEL_URL': CHANNEL_URL,
            'SHOW_START_MENU_ONCE': SHOW_START_MENU_ONCE,
            'SUPPORT': SUPPORT,
            'CHANNEL': CHANNEL,
            'BACK': BACK,
        }
        
        _imports_cached = True
        logger.info("[LegalPolicy] Основные компоненты бота импортированы успешно")
        
    except Exception as e:
        logger.error(f"[LegalPolicy] Ошибка импорта компонентов бота: {e}")
        # Fallback значения
        _import_cache = {
            'get_trial': lambda session, user_id: 0,
            'edit_or_send_message': lambda message, text, reply_markup=None, media_path=None, force_text=False: message.edit_text(text, reply_markup=reply_markup) if message else None,
            'get_about_vpn': lambda version: "🔥 О сервисе\n\nИнформация о нашем VPN сервисе.",
            'DONATIONS_ENABLE': False,
            'SUPPORT_CHAT_URL': "https://t.me/support",
            'CHANNEL_EXISTS': False,
            'CHANNEL_URL': "https://t.me/channel",
            'SHOW_START_MENU_ONCE': True,
            'SUPPORT': "👨‍💻 Поддержка",
            'CHANNEL': "📢 Канал",
            'BACK': "◀️ Назад",
        }
        _imports_cached = True
    
    return _import_cache


def create_legal_policy_buttons():
    """Создает кнопки правовых документов с учетом настроек"""
    buttons = []
    
    if LegalPolicyConfig.USE_WEBAPP_BUTTONS:
        # Создаем WebApp кнопки
        terms_button = InlineKeyboardButton(
            text=LegalPolicyConfig.TERMS_BUTTON_TEXT,
            web_app=WebAppInfo(url=LegalPolicyConfig.TERMS_WEBAPP_URL)
        )
        privacy_button = InlineKeyboardButton(
            text=LegalPolicyConfig.PRIVACY_BUTTON_TEXT,
            web_app=WebAppInfo(url=LegalPolicyConfig.PRIVACY_WEBAPP_URL)
        )
    else:
        # Создаем обычные URL кнопки
        terms_button = InlineKeyboardButton(
            text=LegalPolicyConfig.TERMS_BUTTON_TEXT,
            url=LegalPolicyConfig.TERMS_OF_SERVICE_URL
        )
        privacy_button = InlineKeyboardButton(
            text=LegalPolicyConfig.PRIVACY_BUTTON_TEXT,
            url=LegalPolicyConfig.PRIVACY_POLICY_URL
        )
    
    if LegalPolicyConfig.BUTTONS_INLINE:
        # Кнопки в одной строке
        buttons.append([terms_button, privacy_button])
    else:
        # Кнопки в разных строках
        buttons.append([terms_button])
        buttons.append([privacy_button])
    
    return buttons


@router.callback_query(F.data == "about_vpn")
async def handle_about_vpn_with_legal_policy(callback: CallbackQuery, session: AsyncSession):
    """
    Перехватывает callback "about_vpn" и добавляет кнопки правовых документов
    """
    logger.info("[LegalPolicy] Перехват callback 'about_vpn'")
    
    # Проверяем, включен ли модуль
    if not LegalPolicyConfig.ENABLED:
        logger.warning("[LegalPolicy] Модуль отключен в конфиге!")
        return
    
    try:
        # Получаем импорты через ленивую загрузку
        imports = _lazy_import()
        
        user_id = callback.from_user.id
        
        # Безопасное получение trial с обработкой ошибок
        try:
            trial = await imports['get_trial'](session, user_id)
        except Exception as e:
            logger.warning(f"[LegalPolicy] Ошибка получения trial: {e}, используем значение по умолчанию")
            trial = 0
        
        # Безопасное определение back_target
        back_target = "profile" if imports['SHOW_START_MENU_ONCE'] and trial > 0 else "start"

        kb = InlineKeyboardBuilder()
        
        # Создаем список всех кнопок для правильного порядка
        other_buttons = []
        
        # Добавляем стандартные кнопки из основного обработчика с защитой
        if imports['DONATIONS_ENABLE']:
            other_buttons.append([InlineKeyboardButton(text="💰 Поддержать проект", callback_data="donate")])

        other_buttons.append([InlineKeyboardButton(text=imports['SUPPORT'], url=imports['SUPPORT_CHAT_URL'])])
        
        if imports['CHANNEL_EXISTS']:
            other_buttons.append([InlineKeyboardButton(text=imports['CHANNEL'], url=imports['CHANNEL_URL'])])

        other_buttons.append([InlineKeyboardButton(text=imports['BACK'], callback_data=back_target)])
        
        # Создаем кнопки правовых документов
        legal_buttons = create_legal_policy_buttons()
        
        # Добавляем кнопки в зависимости от позиции
        if LegalPolicyConfig.BUTTONS_POSITION == "top":
            # Сначала правовые кнопки, потом остальные
            all_buttons = legal_buttons + other_buttons
        else:
            # Сначала остальные кнопки, потом правовые
            all_buttons = other_buttons + legal_buttons
        
        # Добавляем все кнопки в клавиатуру
        for button_row in all_buttons:
            kb.row(*button_row)
        
        # Получаем текст из основного обработчика с защитой
        try:
            text = imports['get_about_vpn']("3.2.3-minor")
        except Exception as e:
            logger.warning(f"[LegalPolicy] Ошибка получения текста: {e}, используем текст по умолчанию")
            text = "🔥 О сервисе\n\nИнформация о нашем VPN сервисе."
        
        # Проверяем доступность изображения
        image_path = os.path.join("img", "pic.jpg")
        image_exists = os.path.exists(image_path)
        logger.info(f"[LegalPolicy] Изображение {image_path} {'найдено' if image_exists else 'не найдено'}")
        
        # Отправляем сообщение с защитой
        try:
            await imports['edit_or_send_message'](
                callback.message, 
                text, 
                reply_markup=kb.as_markup(), 
                media_path=image_path if image_exists else None, 
                force_text=False
            )
            logger.info("[LegalPolicy] Сообщение отправлено через edit_or_send_message")
        except Exception as e:
            logger.warning(f"[LegalPolicy] Ошибка отправки через edit_or_send_message: {e}, используем альтернативный метод")
            # Диагностика типа сообщения
            logger.info(f"[LegalPolicy] Диагностика сообщения: has_photo={bool(callback.message.photo)}, has_text={bool(callback.message.text)}, content_type={callback.message.content_type}")
            
            # Fallback на альтернативные методы отправки
            try:
                # Проверяем тип текущего сообщения
                if callback.message.photo:
                    # Если сообщение содержит фото, редактируем caption
                    logger.info("[LegalPolicy] Редактируем caption фото")
                    await callback.message.edit_caption(caption=text, reply_markup=kb.as_markup())
                elif callback.message.text:
                    # Если сообщение содержит текст, редактируем текст
                    logger.info("[LegalPolicy] Редактируем текст сообщения")
                    await callback.message.edit_text(text, reply_markup=kb.as_markup())
                else:
                    # Если неопределенный тип, отправляем новое сообщение
                    logger.info("[LegalPolicy] Отправляем новое сообщение")
                    await callback.message.answer(text, reply_markup=kb.as_markup())
                    
                logger.info("[LegalPolicy] Альтернативная отправка прошла успешно")
            except Exception as e2:
                logger.error(f"[LegalPolicy] Критическая ошибка отправки сообщения: {e2}")
                # Последняя попытка - просто ответить на callback
                try:
                    await callback.answer("Раздел временно недоступен", show_alert=True)
                    logger.info("[LegalPolicy] Отправлен fallback ответ пользователю")
                except Exception as e3:
                    logger.error(f"[LegalPolicy] Даже callback ответ не удался: {e3}")
                return
        
        logger.info("[LegalPolicy] Раздел 'О сервисе' отображен с кнопками правовых документов")
        
    except Exception as e:
        logger.error(f"[LegalPolicy] Ошибка при обработке callback 'about_vpn': {e}")
        logger.exception(e)
        # В случае ошибки - пропускаем обработку, чтобы сработал основной обработчик


async def on_startup():
    """Хук запуска модуля"""
    logger.info("[LegalPolicy] ========== МОДУЛЬ ПРАВОВЫХ ДОКУМЕНТОВ ЗАПУСКАЕТСЯ ==========")
    
    # Инициализируем импорты
    _lazy_import()
    
    logger.info(f"[LegalPolicy] ENABLED: {LegalPolicyConfig.ENABLED}")
    logger.info(f"[LegalPolicy] TERMS_BUTTON_TEXT: {LegalPolicyConfig.TERMS_BUTTON_TEXT}")
    logger.info(f"[LegalPolicy] PRIVACY_BUTTON_TEXT: {LegalPolicyConfig.PRIVACY_BUTTON_TEXT}")
    logger.info(f"[LegalPolicy] TERMS_URL: {LegalPolicyConfig.TERMS_OF_SERVICE_URL}")
    logger.info(f"[LegalPolicy] PRIVACY_URL: {LegalPolicyConfig.PRIVACY_POLICY_URL}")
    logger.info(f"[LegalPolicy] USE_WEBAPP_BUTTONS: {LegalPolicyConfig.USE_WEBAPP_BUTTONS}")
    logger.info(f"[LegalPolicy] BUTTONS_POSITION: {LegalPolicyConfig.BUTTONS_POSITION}")
    logger.info(f"[LegalPolicy] BUTTONS_INLINE: {LegalPolicyConfig.BUTTONS_INLINE}")
    if LegalPolicyConfig.USE_WEBAPP_BUTTONS:
        logger.info(f"[LegalPolicy] TERMS_WEBAPP_URL: {LegalPolicyConfig.TERMS_WEBAPP_URL}")
        logger.info(f"[LegalPolicy] PRIVACY_WEBAPP_URL: {LegalPolicyConfig.PRIVACY_WEBAPP_URL}")
    logger.info("[LegalPolicy] ========== МОДУЛЬ ПРАВОВЫХ ДОКУМЕНТОВ ИНИЦИАЛИЗИРОВАН ==========")


async def on_shutdown():
    """Хук остановки модуля"""
    logger.info("[LegalPolicy] Модуль правовых документов остановлен")


# Регистрируем хуки в роутере
router.startup.register(on_startup)
router.shutdown.register(on_shutdown)
