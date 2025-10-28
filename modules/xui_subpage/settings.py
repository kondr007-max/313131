"""
========================================
📋 ИНСТРУКЦИЯ ПО НАСТРОЙКЕ МОДУЛЯ
========================================

Этот модуль создает красивую веб-страницу для подключения VPN на разных устройствах.
Пользователи смогут легко подключить свои телефоны, компьютеры и даже телевизоры.

🔧 ШАГ 1: УСТАНОВКА
   Папка модуля уже находится в правильном месте (modules/xui_subpage/)

📝 ШАГ 2: НАСТРОЙКА
   Отредактируйте настройки ниже под свои нужды

🌐 ШАГ 3: НАСТРОЙКА ВЕБА (NGINX)
   Откройте файл настроек Nginx:
   sudo nano /etc/nginx/sites-available/default
   
   Добавьте этот блок в секцию server {}:
   location /connect/ {
       proxy_pass http://localhost:3023/connect/;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ВАЖНО: Замените 3023 на ваш MODULE_PORT, если меняли его ниже

🌐 ШАГ 3 (АЛЬТЕРНАТИВА): НАСТРОЙКА ВЕБА (CADDY)
   Если используете Caddy вместо Nginx, откройте:
   sudo nano /etc/caddy/Caddyfile
   
   Добавьте:
   reverse_proxy /connect/* http://localhost:3023
   ВАЖНО: Замените 3023 на ваш MODULE_PORT, если меняли его ниже
   ВАЖНО: Удалите этот блок, если он уже есть в вашем Caddyfile:
    header {
        Content-Type text/plain
        Content-Disposition inline
    }

✅ ШАГ 4: ПРИМЕНЕНИЕ ИЗМЕНЕНИЙ
   Для Nginx: sudo nginx -t && sudo systemctl reload nginx
   Для Caddy: sudo systemctl reload caddy

🚀 ШАГ 5: ПЕРЕЗАПУСК БОТА
   sudo systemctl restart bot.service
   
   После этого в боте появится новая кнопка подключения устройств!
"""

# ========================================
# 🔧 ОСНОВНЫЕ НАСТРОЙКИ
# ========================================

# Включен ли модуль?
# True = работает новая красивая страница подключения
# False = остаются старые кнопки без изменений
MODULE_ENABLED = True

# Какие кнопки показывать в боте?
# "webapp" = WebApp кнопка (открывается внутри Telegram) без дополнительной кнопки
# "web" = URL кнопка (открывается во внешнем браузере) без дополнительной кнопки
# "webapp_extra" = WebApp кнопка (внутри Telegram) + дополнительная inline-кнопка "Другой способ"
# "web_extra" = URL кнопка (внешний браузер) + дополнительная inline-кнопка "Другой способ"
BUTTON_MODE = "webapp"

# На каком порту запускать веб-страницу?
# Обычно 3023 подходит для всех. Меняйте только если порт уже занят (также сменить надо будет в Nginx/Caddy)
MODULE_PORT = 3023


# ======================================
# 🔒 БЕЗОПАСНОСТЬ
# ======================================

# Включить ограничение количества запросов (защита от перебора подписок)
RATE_LIMIT_ENABLED = True

# Максимальное количество запросов к API с одного IP
RATE_LIMIT_REQUESTS = 20

# Период времени для подсчета запросов (в секундах)
RATE_LIMIT_PERIOD = 60

# Время блокировки IP при превышении лимита (в секундах)
RATE_LIMIT_BLOCK_TIME = 60

# Адрес страницы подключения
# Должен совпадать с настройкой в Nginx/Caddy выше. Обычно не нужно менять
BASE_PATH = "/connect/"

# ========================================
# 📝 ТЕКСТЫ НА КНОПКАХ
# ========================================
# Что будет написано на кнопках в боте

CONNECT_DEVICE_WEB = "📲 Подключить устройство"      # Основная кнопка, которая заменяется
CONNECT_DEVICE_EXTRA = "Другой способ подключения"   # Дополнительная кнопка со старой логикой (запасная для устройств, не поддерживающих WebApp)

# ========================================
# 🌍 ЯЗЫКОВЫЕ НАСТРОЙКИ
# ========================================
# Какой язык показывать пользователям на странице подключения

# Как определять язык пользователя?
# "user" = автоматически по языку Telegram пользователя (рекомендуется)
# "ru" = всегда показывать русский язык
# "en" = всегда показывать английский язык
LANGUAGE_MODE = "user"

# Какой язык использовать, если не получилось определить язык пользователя?
# Обычно "ru" подходит для большинства случаев
FALLBACK_LANGUAGE = "ru"

# ========================================
# 🎨 ВНЕШНИЙ ВИД И ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ
# ========================================

# Какую тему оформления использовать?
# "dark" = темная тема
# "light" = светлая тема
# "cyberpunk" = неоновая киберпанк тема
# "ocean" = морская голубая тема
# "fox" = оранжевая "лисья" тема
CURRENT_THEME = "cyberpunk"

# Включить тактильную обратную связь (вибрацию при нажатиях)?
# True = вибрация включена при взаимодействии с интерфейсом
# False = вибрация отключена
HAPTIC_ENABLED = True

# Показывать селектор стран для VLESS ключей? Работает только с 3X-UI и пока не стабильно - тестируйте!
# True = показывать селектор стран для VLESS-ссылок
# False = скрывать селектор стран для VLESS-ссылок
VLESS_SELECTOR_ENABLED = False

# ========================================
# 📱 КАКИЕ ПРИЛОЖЕНИЯ ПОКАЗЫВАТЬ ПОЛЬЗОВАТЕЛЯМ
# ========================================
# Здесь настраивается, какие VPN-приложения предлагать для каждого типа устройства
# 0 = приложение скрыто
# 1, 2, 3... = порядок показа (1 = первое, 2 = второе и т.д.)

APPS_ENABLED = {
    "ios": {"Happ": 1, "V2rayTun": 2, "Shadowrocket": 0, "Streisand": 0, "Singbox": 0, "ClashMi": 0},                                # iPhone/iPad
    "android": {"Happ": 1, "Hiddify": 0, "V2rayTun": 2, "FlClashX": 0, "ClashMeta": 0, "Singbox": 0, "V2rayNG": 0, "Exclave": 0},    # Android телефоны
    "windows": {"Happ": 1, "Hiddify": 0, "V2rayTun": 2, "Koalaclash": 0, "FlClashX": 0, "ClashVerge": 0},                            # Windows компьютеры
    "macos": {"Happ": 1, "Hiddify": 0, "Shadowrocket": 0, "V2rayTun": 0, "Koalaclash": 0, "ClashVerge": 0, "Singbox": 0},            # Mac компьютеры
    "linux": {"Hiddify": 0, "Happ": 1},     # Linux компьютеры
    "appletv": {"Happ": 1},                 # Apple TV
    "androidtv": {"Happ": 1}                # Android TV
}

# ========================================
# 🔘 КАКИЕ КНОПКИ СКАЧИВАНИЯ ПОКАЗЫВАТЬ
# ========================================
# Для каждого приложения может быть несколько вариантов скачивания
# 
# 0 = кнопка скрыта
# 1, 2, 3... = порядок показа кнопок (1 = первая, 2 = вторая)

BUTTONS_ENABLED = {
    "ios": {                                        # iPhone/iPad
        "happ_1": 1, "happ_2": 2,                   # Happ: русский App Store (1) + мировой App Store (2)
        "v2raytun_1": 1,                            # V2rayTun: App Store
        "shadowrocket_1": 1,                        # Shadowrocket: App Store
        "streisand_1": 1,                           # Streisand: App Store
        "singbox_1": 1,                             # sing-box: App Store
        "clashmi_1": 1                              # Clash Mi: App Store
    },
    "android": {                                    # Android телефоны
        "happ_1": 1, "happ_2": 2,                   # Happ: Google Play (1) + APK файл (2)
        "hiddify_1": 1,                             # Hiddify: APK файл
        "v2raytun_1": 1, "v2raytun_2": 2,           # V2rayTun: Google Play (1) + APK файл (2)
        "flclashx_1": 1,                            # FlClashX: APK файл
        "clashmeta_1": 1,                           # Clash Meta: APK файл
        "singbox_1": 1, "singbox_2": 2,             # sing-box: Google Play (1) + APK файл (2)
        "v2rayng_1": 1,                             # v2rayNG: APK файл
        "exclave_1": 1                              # Exclave: APK файл
    },
    "windows": {                                    # Windows компьютеры
        "happ_1": 1,                                # Happ: установщик exe
        "hiddify_1": 1,                             # Hiddify: установщик exe
        "v2raytun_1": 1,                            # V2rayTun: установщик exe
        "koalaclash_1": 1,                          # Koala Clash: установщик exe
        "flclashx_1": 1,                            # FlClashX: установщик exe
        "clashverge_1": 1                           # Clash Verge: установщик exe
    },
    "macos": {                                      # Mac компьютеры
        "happ_1": 1, "happ_2": 2,                   # Happ: русский App Store (1) + мировой App Store (2)
        "hiddify_1": 1,                             # Hiddify: DMG файл
        "v2raytun_1": 1,                            # V2rayTun: App Store
        "shadowrocket_1": 1,                        # Shadowrocket: App Store
        "koalaclash_1": 1,                          # Koala Clash: DMG файл
        "singbox_1": 1,                             # sing-box: App Store
        "clashverge_1": 1, "clashverge_2": 2        # Clash Verge: Intel (1) + M-series (2)
    },
    "linux": {                                      # Linux компьютеры
        "hiddify_1": 1,                             # Hiddify: AppImage файл
        "happ_1": 1                                 # Happ: AppImage файл

    },
    "appletv": {"happ_1": 1},                       # Apple TV: только Happ
    "androidtv": {"happ_1": 1}                      # Android TV: только Happ
}

# ========================================
# 📥 ССЫЛКИ ДЛЯ СКАЧИВАНИЯ ПРИЛОЖЕНИЙ
# ========================================
# Здесь указаны прямые ссылки на магазины и сайты для скачивания приложений
# Пользователи увидят кнопки "Скачать" с этими ссылками
# 
# ВНИМАНИЕ: Ссылки могут устареть! Периодически проверяйте их актуальность
# Если какая-то ссылка не работает, найдите новую

APP_LINKS = {
    # === iPhone и iPad ===
    "ios": {
        "happ_1": "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",      # Happ (русский App Store)
        "happ_2": "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",           # Happ (мировой App Store)
        "v2raytun_1": "https://apps.apple.com/ru/app/v2raytun/id6476628951",                 # V2rayTun
        "shadowrocket_1": "https://apps.apple.com/ru/app/shadowrocket/id932747118",          # Shadowrocket (платное)
        "streisand_1": "https://apps.apple.com/us/app/streisand/id6450534064",               # Streisand
        "singbox_1": "https://apps.apple.com/app/sing-box-vt/id6673731168",                  # sing-box
        "clashmi_1": "https://apps.apple.com/ru/app/clash-mi/id6744321968"                      # Clash Mi
    },
    
    # === Android телефоны ===
    "android": {
        "happ_1": "https://play.google.com/store/apps/details?id=com.happproxy",                                                    # Happ (Google Play)
        "happ_2": "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ_beta.apk",                              # Happ (прямая ссылка APK)
        "hiddify_1": "https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-Android-universal.apk",              # Hiddify APK
        "v2raytun_1": "https://play.google.com/store/apps/details?id=com.v2raytun.android",                                         # V2rayTun (Google Play)
        "v2raytun_2": "https://github.com/ADDVPN/v2raytun/releases/download/v1.3/v2RayTun_universal_3_12_46.apk",                   # V2rayTun APK
        "flclashx_1": "https://github.com/pluralplay/FlClashX/releases/download/v0.2.0/FlClashX-0.2.0-android-arm64-v8a.apk",       # FlClashX APK
        "clashmeta_1": "https://github.com/MetaCubeX/ClashMetaForAndroid/releases/download/v2.11.15/cmfa-2.11.15-meta-universal-release.apk",  # Clash Meta APK
        "singbox_1": "https://play.google.com/store/apps/details?id=io.nekohasekai.sfa",                                            # sing-box (Google Play)
        "singbox_2": "https://github.com/SagerNet/sing-box/releases/download/v1.11.10/SFA-1.11.10-universal.apk",                   # sing-box APK
        "v2rayng_1": "https://github.com/2dust/v2rayNG/releases/download/1.10.1/v2rayNG_1.10.1_universal.apk",                      # v2rayNG APK
        "exclave_1": "https://github.com/dyhkwong/Exclave/releases/download/0.14.5/Exclave-0.14.5-arm64-v8a.apk"                    # Exclave APK
    },
    
    # === Windows компьютеры ===
    "windows": {
        "happ_1": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x86.exe",                         # Happ установщик
        "hiddify_1": "https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-Windows-Setup-x64.exe",              # Hiddify установщик
        "v2raytun_1": "https://storage.v2raytun.com/v2RayTun_Setup.exe",                                                            # V2rayTun установщик
        "koalaclash_1": "https://github.com/coolcoala/clash-verge-rev-lite/releases/latest/download/Koala.Clash_x64-setup.exe",     # Koala Clash установщик
        "flclashx_1": "https://github.com/pluralplay/FlClashX/releases/download/v0.2.0/FlClashX-0.2.0-windows-amd64-setup.exe",     # FlClashX установщик
        "clashverge_1": "https://github.com/clash-verge-rev/clash-verge-rev/releases/download/v2.2.2/Clash.Verge_2.2.2_x64-setup.exe"  # Clash Verge установщик
    },
    
    # === Mac компьютеры ===
    "macos": {
        "happ_1": "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",                                             # Happ (русский App Store)
        "happ_2": "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",                                                  # Happ (мировой App Store)
        "hiddify_1": "https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-MacOS.dmg",                          # Hiddify установщик
        "v2raytun_1": "https://apps.apple.com/ru/app/v2raytun/id6476628951",                                                        # V2rayTun (App Store)
        "shadowrocket_1": "https://apps.apple.com/ru/app/shadowrocket/id932747118",                                                 # Shadowrocket для  (App Store для M1-M4)
        "koalaclash_1": "https://github.com/coolcoala/clash-verge-rev-lite/releases/latest/download/Koala.Clash_x64.dmg",           # Koala Clash DMG файл
        "singbox_1": "https://apps.apple.com/app/sing-box-vt/id6673731168",                                                         # sing-box (App Store)
        "clashverge_1": "https://github.com/clash-verge-rev/clash-verge-rev/releases/download/v2.2.2/Clash.Verge_2.2.2_x64.dmg",    # Clash Verge (Intel)
        "clashverge_2": "https://github.com/clash-verge-rev/clash-verge-rev/releases/download/v2.2.2/Clash.Verge_2.2.2_aarch64.dmg" # Clash Verge (M-series)
    },
    
    # === Linux компьютеры ===
    "linux": {
        "hiddify_1": "https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-Linux-x64.AppImage",                 # Hiddify (универсальный файл)
        "happ_1": "https://github.com/Happ-proxy/happ-desktop/releases/download/alpha_0.3.7/Happ.linux.x86.AppImage"                # Happ (универсальный файл)
    }
}

# ========================================
# 🔗 ССЫЛКИ ДЛЯ АВТОМАТИЧЕСКОГО ДОБАВЛЕНИЯ ПОДПИСКИ
# ========================================
# Специальные ссылки, с помощью которых подписка автоматически добавляется в приложение
# Обычно не нужно менять - это стандартные адреса для каждого приложения

DEEPLINKS = {
    "happ": "happ://add/",                                # Ссылка для Happ
    "hiddify": "hiddify://import/",                       # Ссылка для Hiddify
    "v2raytun": "v2raytun://import/",                     # Ссылка для V2rayTun
    "shadowrocket": "shadowrocket://add/",                # Ссылка для Shadowrocket
    "streisand": "streisand://import/",                   # Ссылка для Streisand
    "clash": "clash://install-config?url=",               # Ссылка для Koala Clash, Clash Verge, Clash Meta, FlClashX, Clash Mi
    "singbox": "sing-box://import-remote-profile/?url=",  # Ссылка для sing-box
    "v2rayng": "v2rayng://install-config?url=",           # Ссылка для v2rayNG
    "exclave": "exclave://subscription?url="              # Ссылка для Exclave
}

# ========================================
# ✅ НАСТРОЙКА ЗАВЕРШЕНА
# ========================================
# После изменения настроек не забудьте:
# 1. Сохранить файл (Ctrl+S)
# 2. Перезапустить бота: sudo systemctl restart bot.service


