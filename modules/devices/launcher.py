"""
Простая система для запуска мониторинга устройств
"""

import asyncio
from logger import logger
from .settings import ENABLE_NEW_DEVICE_NOTIFICATIONS

# Глобальная переменная для хранения бота
_bot_instance = None
_monitoring_started = False


def set_bot_instance(bot):
    """Устанавливает экземпляр бота для мониторинга"""
    global _bot_instance
    _bot_instance = bot
    logger.info(f"[devices] Установлен экземпляр бота: {bot}")
    
    # Запускаем мониторинг, если он еще не запущен
    if ENABLE_NEW_DEVICE_NOTIFICATIONS and not _monitoring_started:
        asyncio.create_task(_start_monitoring_delayed())


def get_bot_instance():
    """Возвращает текущий экземпляр бота"""
    global _bot_instance
    
    # Если бот не установлен, пытаемся его найти
    if _bot_instance is None:
        logger.info("[devices] Bot instance не найден, пытаемся автообнаружение...")
        
        # Простое автообнаружение через импорт
        try:
            import bot as bot_module
            if hasattr(bot_module, 'bot'):
                _bot_instance = bot_module.bot
                logger.info(f"[devices] ✅ Найден bot через автообнаружение: {_bot_instance}")
            else:
                logger.warning("[devices] Модуль bot найден, но переменная bot отсутствует")
        except ImportError:
            logger.warning("[devices] Не удалось импортировать модуль bot")
            
        # Пытаемся найти через sys.modules
        if _bot_instance is None:
            import sys
            for name, module in sys.modules.items():
                if hasattr(module, 'bot') and name in ['bot', '__main__']:
                    candidate = getattr(module, 'bot')
                    if hasattr(candidate, 'token') or hasattr(candidate, 'session'):
                        _bot_instance = candidate
                        logger.info(f"[devices] ✅ Найден bot в модуле {name}: {_bot_instance}")
                        break
    
    return _bot_instance


async def _start_monitoring_delayed():
    """Запускает мониторинг с небольшой задержкой"""
    global _monitoring_started
    
    if _monitoring_started:
        return
        
    _monitoring_started = True
    
    # Ждем 60 секунд, чтобы бот полностью загрузился
    await asyncio.sleep(60)
    
    try:
        if _bot_instance:
            logger.info("[devices] Запускаем мониторинг устройств...")
            await device_monitor.start_monitoring(_bot_instance)
        else:
            logger.error("[devices] Бот не установлен, мониторинг не запущен")
    except Exception as e:
        logger.error(f"[devices] Ошибка запуска мониторинга: {e}", exc_info=True)


# Функция для автоматического поиска и установки бота
async def auto_detect_bot():
    """Пытается автоматически найти экземпляр бота"""
    import sys
    
    # Проходим по всем загруженным модулям
    for name, module in sys.modules.items():
        if hasattr(module, 'bot'):
            bot = getattr(module, 'bot')
            # Проверяем, что это действительно бот Telegram
            if hasattr(bot, 'session') or hasattr(bot, 'token'):
                logger.info(f"[devices] Найден бот в модуле {name}")
                set_bot_instance(bot)
                return bot
    
    logger.warning("[devices] Автоматическое обнаружение бота не удалось")
    return None


# Автоматическое обнаружение бота будет запущено при вызове функций модуля
if ENABLE_NEW_DEVICE_NOTIFICATIONS:
    logger.info("[devices] Launcher готов к автоматическому обнаружению бота")