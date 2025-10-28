# Модуль устройств - настройки для HTTP webhook режима
# Этот модуль работает через HTTP webhook от панели Remnawave

# Основные настройки
ENABLE_DEVICES_COMMAND = True  # Включить команду /devices
ENABLE_DEVICES_BUTTON_IN_PROFILE = True  # Кнопка "Устройства" в профиле
ENABLE_DEVICES_BUTTON_IN_SUBSCRIPTION = True  # Кнопка "Устройства" в меню подписки
DEVICES_BUTTON_PRIORITY = "profile"  # Приоритет отображения: "profile" или "subscription"

# HTTP Webhook настройки
USE_HTTP_WEBHOOK = True  # Если включены уведомления о новых устройствах - True , иначе False
WEBHOOK_PATH = "/devices/webhook"  # Путь для получения уведомлений от панели

# Настройки уведомлений
ENABLE_NEW_DEVICE_NOTIFICATIONS = True  # Включить уведомления о новых устройствах
NOTIFICATION_SETTINGS_IN_MENU = True  # Кнопка настроек уведомлений в меню устройств

# Настройки удаления устройств
DELETE_DEVICE_COOLDOWN_MINUTES = 0  # Кулдаун между удалениями устройств (в минутах). 0 - без кулдауна