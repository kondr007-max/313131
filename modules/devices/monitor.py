"""
Заглушки для совместимости с HTTP webhook режимом
В HTTP webhook режиме мониторинг не используется - всё работает через /devices/webhook
"""

# Заглушки для совместимости
device_monitor = None

# Простое хранение настроек уведомлений в памяти
_user_notification_settings = {}

def get_user_notification_setting(tg_id: int) -> bool:
    """Возвращает настройку уведомлений пользователя (по умолчанию включены)"""
    return _user_notification_settings.get(tg_id, True)

def set_user_notification_setting(tg_id: int, enabled: bool) -> bool:
    """Сохраняет настройку уведомлений пользователя"""
    _user_notification_settings[tg_id] = enabled
    return True

async def start_device_monitoring(bot):
    """Заглушка - в HTTP webhook режиме не используется"""
    pass

def stop_device_monitoring():
    """Заглушка - в HTTP webhook режиме не используется"""
    pass