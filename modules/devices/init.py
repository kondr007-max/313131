"""
Инициализация модуля devices - HTTP webhook режим
"""

from logger import logger
from .settings import ENABLE_NEW_DEVICE_NOTIFICATIONS

_devices_initialized = False


async def init_devices_module(bot):
    """Инициализирует модуль devices в HTTP webhook режиме"""
    global _devices_initialized
    try:
        logger.info(f"[devices] Инициализация модуля devices с ботом: {bot}")
        
        # Защита от повторной инициализации
        if _devices_initialized:
            logger.info("[devices] Модуль уже инициализирован, пропускаем")
            return
        
        if ENABLE_NEW_DEVICE_NOTIFICATIONS:
            logger.info("[devices] ✅ HTTP webhook режим активирован")
            logger.info("[devices] ✅ Webhook будет обрабатывать уведомления на /devices/webhook")
            logger.info("[devices] ✅ Модуль devices готов к работе")
            
            # Отмечаем, что модуль инициализирован
            _devices_initialized = True
        else:
            logger.info("[devices] Уведомления о новых устройствах отключены в настройках")
            
    except Exception as e:
        logger.error(f"[devices] Ошибка инициализации модуля: {e}", exc_info=True)


async def shutdown_devices_module():
    """Завершает работу модуля devices"""
    logger.info("[devices] Модуль остановлен")


# Хук для автоинициализации модуля при запуске бота
def register_device_module_hooks():
    """Регистрирует хуки модуля devices"""
    try:
        from hooks.hooks import register_hook
        
        # Используем хук periodic_notifications для инициализации
        async def periodic_devices_hook(**kwargs):
            """Хук для инициализации модуля devices"""
            bot = kwargs.get('bot')
            if bot and ENABLE_NEW_DEVICE_NOTIFICATIONS:
                try:
                    await init_devices_module(bot)
                except Exception as e:
                    logger.error(f"[devices] Ошибка в periodic_devices_hook: {e}", exc_info=True)
            
        # Регистрируем хук
        register_hook("periodic_notifications", periodic_devices_hook)
        logger.info("[devices] Хуки модуля зарегистрированы")
        
    except Exception as e:
        logger.warning(f"[devices] Не удалось зарегистрировать хуки: {e}")


# Автоматическая регистрация хуков при импорте модуля
if ENABLE_NEW_DEVICE_NOTIFICATIONS:
    register_device_module_hooks()
    logger.info("[devices] HTTP webhook режим готов к запуску")