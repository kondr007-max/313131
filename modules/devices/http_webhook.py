"""
HTTP Webhook handler for real-time HWID device notifications
"""

from aiogram import Router
from aiogram.types import Message
from logger import logger
from .database_helper import get_key_by_client_id
from .texts import NEW_DEVICE_NOTIFICATION
import json

# Создаем router для webhook
webhook_router = Router()

async def handle_hwid_webhook(payload: dict, bot):
    """
    Обрабатывает HTTP webhook уведомления о новых HWID устройствах
    
    Args:
        payload (dict): Данные о новом устройстве
        bot: Экземпляр бота для отправки уведомлений
    """
    try:
        logger.info(f"[devices] 🚀 НАЧАЛО ОБРАБОТКИ HWID WEBHOOK")
        
        user_uuid = payload.get('user_uuid')
        device_id = payload.get('device_id')
        hwid = payload.get('hwid')
        device_model = payload.get('device_model', '—')
        platform = payload.get('platform', '—')
        os_version = payload.get('os_version', '—')
        user_agent = payload.get('user_agent', '—')
        connected_at = payload.get('connected_at', '')
        
        logger.info(f"[devices] 🚨 HTTP WEBHOOK - Новое HWID устройство: {hwid} для пользователя {user_uuid}")
        
        # Получаем информацию о ключе пользователя
        logger.info(f"[devices] 🔍 Поиск ключа для client_id: {user_uuid}")
        key_info = await get_key_by_client_id(user_uuid)
        
        if not key_info:
            logger.warning(f"[devices] ❌ Ключ с client_id {user_uuid} не найден в базе")
            return
            
        tg_id = key_info.get('tg_id')
        logger.info(f"[devices] 👤 Найден пользователь tg_id: {tg_id}")
        
        # Проверяем, включены ли уведомления для пользователя
        from .monitor import get_user_notification_setting
        notifications_enabled = get_user_notification_setting(tg_id)
        logger.info(f"[devices] 🔔 Уведомления для пользователя {tg_id}: {'включены' if notifications_enabled else 'отключены'}")
        
        if not notifications_enabled:
            logger.info(f"[devices] ⏩ Уведомления отключены для пользователя {tg_id}, пропускаем")
            return
        
        # Форматируем время
        if connected_at:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(connected_at.replace('Z', '+00:00'))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                formatted_time = connected_at[:19].replace('T', ' ')
        else:
            formatted_time = '—'
        
        # Формируем уведомление
        notification_text = NEW_DEVICE_NOTIFICATION.format(
            email=key_info.get('key_name', '—'),
            device_model=device_model,
            platform=f"{platform} / {os_version}",
            user_agent=user_agent,
            connected_at=formatted_time
        )
        
        # Отправляем уведомление
        logger.info(f"[devices] 📤 Отправляем уведомление пользователю {tg_id}")
        logger.info(f"[devices] 📝 Текст уведомления: {notification_text[:100]}...")
        
        await bot.send_message(tg_id, notification_text)
        logger.info(f"[devices] ✅ HTTP WEBHOOK уведомление отправлено пользователю {tg_id}")
        
    except Exception as e:
        logger.error(f"[devices] ❌ Ошибка обработки HTTP webhook: {e}", exc_info=True)


# Функция get_webhook_data() перенесена в router.py для избежания конфликтов


async def hwid_webhook_handler(request):
    """
    HTTP обработчик webhook уведомлений от Remnawave панели
    """
    try:
        # Получаем JSON из запроса
        payload = await request.json()
        
        # Получаем экземпляр бота (нужно будет добавить в контекст)
        from .launcher import get_bot_instance
        bot = get_bot_instance()
        
        if not bot:
            logger.error("[devices] Bot instance не найден для HTTP webhook")
            return {"status": "error", "message": "Bot not available"}
        
        # Обрабатываем webhook
        await handle_hwid_webhook(payload, bot)
        
        return {"status": "success", "message": "Webhook processed"}
        
    except Exception as e:
        logger.error(f"[devices] Ошибка HTTP webhook handler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}