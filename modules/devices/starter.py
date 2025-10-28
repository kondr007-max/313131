"""
Простой запуск мониторинга устройств
"""

from logger import logger
from .settings import ENABLE_NEW_DEVICE_NOTIFICATIONS
from .monitor import device_monitor

# Глобальная переменная для отслеживания состояния запуска
_monitoring_initialized = False


async def start_monitoring_if_needed(bot):
    """Запускает мониторинг, если он еще не запущен"""
    global _monitoring_initialized
    
    if not ENABLE_NEW_DEVICE_NOTIFICATIONS:
        return
        
    if _monitoring_initialized:
        return
        
    if device_monitor.is_running:
        return
        
    try:
        _monitoring_initialized = True
        logger.info("[devices] Инициализируем мониторинг устройств...")
        
        # Загружаем настройки пользователей
        await device_monitor.load_user_settings()
        
        # Запускаем мониторинг в отдельной задаче
        import asyncio
        task = asyncio.create_task(device_monitor.start_monitoring(bot))
        logger.info(f"[devices] Создана задача мониторинга: {task}")
        
    except Exception as e:
        logger.error(f"[devices] Ошибка запуска мониторинга: {e}", exc_info=True)
        _monitoring_initialized = False  # Сбрасываем флаг при ошибке