# HTTP webhook режим - только необходимые компоненты
from .init import init_devices_module, shutdown_devices_module
from .launcher import set_bot_instance, auto_detect_bot

# Автоматические импорты для инициализации
from . import init
from . import launcher
# Убираем проблематичный импорт main_webhook_hook

__all__ = ("router", "init_devices_module", "shutdown_devices_module", "set_bot_instance", "auto_detect_bot")
from .router import router