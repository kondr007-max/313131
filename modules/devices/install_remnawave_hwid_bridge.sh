#!/bin/bash
# Универсальный установщик HWID уведомлений для панели Remnawave
# Поддерживает любые домены и автоматически находит настройки PostgreSQL

set -e  # Остановить выполнение при ошибке

echo "🚀 Универсальный установщик HWID уведомлений для Remnawave"
echo "============================================================"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода цветного текста
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_question() {
    echo -e "${BLUE}[INPUT]${NC} $1"
}

# 1. Проверка что мы в правильной директории
if [ ! -d "/opt/remnawave" ]; then
    print_error "Директория /opt/remnawave не найдена!"
    print_error "Пожалуйста, запустите скрипт на сервере с установленной панелью Remnawave."
    exit 1
fi

cd /opt/remnawave
print_status "Работаем в директории: $(pwd)"

# 2. Поиск файла .env и извлечение настроек PostgreSQL
ENV_FILE=""
if [ -f ".env" ]; then
    ENV_FILE=".env"
elif [ -f "docker-compose.yml" ]; then
    print_warning "Файл .env не найден, попробуем извлечь данные из docker-compose.yml"
else
    print_error "Не найден ни .env, ни docker-compose.yml файл!"
    exit 1
fi

# Функция для извлечения значения из .env
get_env_value() {
    local key="$1"
    local file="$2"
    
    if [ -f "$file" ]; then
        grep "^${key}=" "$file" | cut -d'=' -f2- | sed 's/^"//;s/"$//' | head -n1
    fi
}

# Извлекаем настройки PostgreSQL
if [ -n "$ENV_FILE" ]; then
    print_status "Извлекаем настройки PostgreSQL из $ENV_FILE..."
    
    POSTGRES_USER=$(get_env_value "POSTGRES_USER" "$ENV_FILE")
    POSTGRES_PASSWORD=$(get_env_value "POSTGRES_PASSWORD" "$ENV_FILE")
    POSTGRES_DB=$(get_env_value "POSTGRES_DB" "$ENV_FILE")
    POSTGRES_PORT=$(get_env_value "POSTGRES_PORT" "$ENV_FILE")
    
    # Значения по умолчанию
    POSTGRES_HOST="127.0.0.1"
    POSTGRES_PORT="${POSTGRES_PORT:-6767}"
    POSTGRES_DB="${POSTGRES_DB:-postgres}"
    
    print_status "PostgreSQL найден:"
    print_status "  Host: $POSTGRES_HOST"
    print_status "  Port: $POSTGRES_PORT"
    print_status "  Database: $POSTGRES_DB"
    print_status "  User: $POSTGRES_USER"
else
    print_error "Не удалось найти настройки PostgreSQL!"
    exit 1
fi

# 3. Запрос URL webhook от пользователя
echo ""
print_status "Теперь нужно указать домен вашего Telegram бота"
print_status "Это тот адрес, где работает ваш бот с модулем devices"
echo ""
print_question "Введите домен вашего Telegram бота:"
echo -e "${BLUE}   Пример:${NC}"
echo "   • https://bot.mydomain.ru"  
echo ""
echo -n "URL бота: "
read -r BOT_URL

if [ -z "$BOT_URL" ]; then
    print_error "URL бота не может быть пустым!"
    exit 1
fi

# Проверяем формат URL
if [[ ! "$BOT_URL" =~ ^https?:// ]]; then
    print_error "URL должен начинаться с http:// или https://"
    exit 1
fi

# Убираем trailing slash если есть
BOT_URL="${BOT_URL%/}"
WEBHOOK_URL="${BOT_URL}/devices/webhook"

print_status "Webhook URL: $WEBHOOK_URL"

# 4. Создание Python скрипта webhook bridge (простая версия)
print_status "Создаем PostgreSQL -> HTTP Webhook мост (простая версия)..."

cat > hwid_webhook_bridge.py << EOF
#!/usr/bin/env python3
"""
Простой PostgreSQL -> HTTP Webhook мост для HWID уведомлений Remnawave
Использует стандартные библиотеки Python + psycopg2 + requests
"""

import psycopg2
import psycopg2.extensions
import requests
import json
import logging
import time
import threading
from datetime import datetime

# Настройки подключения (автоматически заполняются установщиком)
POSTGRES_HOST = "$POSTGRES_HOST"
POSTGRES_PORT = $POSTGRES_PORT
POSTGRES_USER = "$POSTGRES_USER"
POSTGRES_PASSWORD = "$POSTGRES_PASSWORD"
POSTGRES_DATABASE = "$POSTGRES_DB"

WEBHOOK_URL = "$WEBHOOK_URL"
LOG_FILE = "/var/log/hwid_webhook_bridge.log"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PostgreSQLWebhookBridge:
    """Простой мост между PostgreSQL NOTIFY и HTTP webhook"""
    
    def __init__(self):
        self.connection = None
        self.is_running = False
        
    def start_bridge(self):
        """Запускает мост"""
        self.is_running = True
        logger.info("🚀 Запускаем PostgreSQL -> HTTP Webhook мост...")
        logger.info(f"📡 Webhook URL: {WEBHOOK_URL}")
        
        max_retries = 10
        retry_count = 0
        
        while self.is_running and retry_count < max_retries:
            try:
                # Подключаемся к PostgreSQL
                self.connection = psycopg2.connect(
                    host=POSTGRES_HOST,
                    port=POSTGRES_PORT,
                    user=POSTGRES_USER,
                    password=POSTGRES_PASSWORD,
                    database=POSTGRES_DATABASE
                )
                self.connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                logger.info("✅ Подключено к PostgreSQL")
                
                # Создаем курсор
                cursor = self.connection.cursor()
                
                # Слушаем канал http_webhook_channel
                cursor.execute("LISTEN http_webhook_channel;")
                logger.info("👂 Слушаем канал http_webhook_channel...")
                
                # Ждем уведомления
                while self.is_running:
                    if self.connection.poll() == psycopg2.extensions.POLL_OK:
                        while self.connection.notifies:
                            notify = self.connection.notifies.pop(0)
                            self.handle_notification(notify)
                    
                    time.sleep(0.1)  # Небольшая пауза чтобы не нагружать CPU
                    
            except Exception as e:
                retry_count += 1
                logger.error(f"❌ Ошибка моста (попытка {retry_count}/{max_retries}): {e}")
                
                if self.connection:
                    try:
                        self.connection.close()
                    except:
                        pass
                
                if retry_count < max_retries:
                    time.sleep(5 * retry_count)  # Экспоненциальная задержка
                else:
                    logger.error("💥 Мост остановлен после максимального количества попыток")
                    break
                    
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
                
    def handle_notification(self, notify):
        """Обрабатывает уведомление от PostgreSQL триггера"""
        try:
            payload = notify.payload
            logger.info(f"📨 Получено уведомление от PostgreSQL: {payload[:100]}...")
            
            # Парсим JSON с данными для HTTP запроса
            notification_data = json.loads(payload)
            url = notification_data.get('url')
            method = notification_data.get('method', 'POST')
            headers = notification_data.get('headers', {})
            body = notification_data.get('body')
            
            if url and body:
                # Отправляем HTTP запрос в отдельном потоке
                thread = threading.Thread(
                    target=self.send_http_request, 
                    args=(url, method, headers, body)
                )
                thread.daemon = True
                thread.start()
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки уведомления: {e}")
            
    def send_http_request(self, url, method, headers, body):
        """Отправляет HTTP запрос на webhook бота"""
        try:
            # Парсим body как JSON если это строка
            if isinstance(body, str):
                body_data = json.loads(body)
            else:
                body_data = body
                
            logger.info(f"🚀 Отправляем HTTP {method} на {url}")
            logger.info(f"📦 Данные: user_uuid={body_data.get('user_uuid')}, hwid={body_data.get('hwid')}")
            
            # Отправляем запрос
            response = requests.request(
                method=method,
                url=url,
                json=body_data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"✅ HTTP запрос успешен: {response.status_code}")
                logger.info(f"📄 Ответ: {response.text[:200]}")
            else:
                logger.warning(f"⚠️ HTTP запрос вернул статус: {response.status_code}")
                logger.warning(f"📄 Ответ: {response.text[:200]}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка HTTP запроса: {e}")
            
    def stop_bridge(self):
        """Останавливает мост"""
        self.is_running = False
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
        logger.info("🛑 PostgreSQL -> HTTP мост остановлен")


def main():
    """Главная функция"""
    bridge = PostgreSQLWebhookBridge()
    
    try:
        bridge.start_bridge()
    except KeyboardInterrupt:
        logger.info("👋 Получен сигнал остановки...")
        bridge.stop_bridge()
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        bridge.stop_bridge()


if __name__ == "__main__":
    print("🌉 PostgreSQL -> HTTP Webhook Bridge для HWID уведомлений")
    print("📡 Отправляет уведомления о новых HWID устройствах в Telegram бот")
    print("🔗 https://github.com/remnawave")
    print()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Остановлено пользователем")
    except Exception as e:
        print(f"\n💥 Ошибка: {e}")
EOF

chmod +x hwid_webhook_bridge.py
print_status "✅ Создан файл hwid_webhook_bridge.py"

# 5. Создание systemd сервиса
print_status "Создаем systemd сервис..."

cat > hwid-webhook-bridge.service << EOF
[Unit]
Description=Remnawave HWID Webhook Bridge - PostgreSQL to Telegram Bot notifications
After=network.target docker.service
Wants=network.target
Requires=docker.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/remnawave
ExecStart=/usr/bin/python3 /opt/remnawave/hwid_webhook_bridge.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Переменные окружения
Environment=PYTHONUNBUFFERED=1

# Безопасность
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

print_status "✅ Создан файл сервиса hwid-webhook-bridge.service"

# 6. Установка Python зависимостей
print_status "Устанавливаем Python зависимости..."

# Определяем операционную систему
if command -v apt &> /dev/null; then
    # Ubuntu/Debian
    print_status "Обнаружена система на базе Debian/Ubuntu"
    apt update
    apt install -y python3-psycopg2 python3-requests
    print_status "✅ Зависимости установлены через apt (системные пакеты)"
elif command -v yum &> /dev/null; then
    # CentOS/RHEL
    print_status "Обнаружена система на базе RedHat/CentOS"
    yum install -y python3-psycopg2 python3-requests
    print_status "✅ Зависимости установлены через yum"
elif command -v pip3 &> /dev/null; then
    # Попытка через pip3 с обходом ограничений
    print_status "Пытаемся установить через pip3..."
    if pip3 install psycopg2-binary requests --break-system-packages 2>/dev/null; then
        print_status "✅ Зависимости установлены через pip3 (с --break-system-packages)"
    elif pip3 install psycopg2-binary requests --user 2>/dev/null; then
        print_status "✅ Зависимости установлены через pip3 (пользовательские пакеты)"
    else
        print_warning "Не удалось установить через pip3"
        print_warning "Попробуйте вручную: apt install python3-psycopg2 python3-requests"
    fi
else
    print_warning "Не удалось автоматически установить зависимости Python"
    print_warning "Пожалуйста, установите вручную:"
    print_warning "  Ubuntu/Debian: apt install python3-psycopg2 python3-requests"
    print_warning "  CentOS/RHEL: yum install python3-psycopg2 python3-requests"
fi

# 7. Создание PostgreSQL триггера
print_status "Создаем PostgreSQL триггер для HWID уведомлений..."

# Временный файл с SQL командами
cat > setup_hwid_trigger.sql << EOF
-- Создание функции триггера для HTTP webhook уведомлений
CREATE OR REPLACE FUNCTION notify_hwid_device_http()
RETURNS TRIGGER AS \$\$
DECLARE
    payload JSON;
    webhook_url TEXT := '$WEBHOOK_URL';
BEGIN
    -- Формируем JSON payload с данными о новом устройстве
    payload := json_build_object(
        'type', 'hwid_device_connected',
        'user_uuid', NEW.user_uuid,
        'hwid', NEW.hwid,
        'device_model', COALESCE(NEW.device_model, '—'),
        'platform', COALESCE(NEW.platform, '—'),
        'os_version', COALESCE(NEW.os_version, '—'),
        'user_agent', COALESCE(NEW.user_agent, '—'),
        'connected_at', NEW.created_at::text,
        'timestamp', EXTRACT(EPOCH FROM NOW())
    );
    
    -- Логируем в PostgreSQL лог
    RAISE LOG 'HWID Device HTTP Webhook: Sending notification for device % of user %', NEW.hwid, NEW.user_uuid;
    
    -- Отправляем HTTP POST запрос асинхронно через NOTIFY
    PERFORM pg_notify('http_webhook_channel', 
        json_build_object(
            'url', webhook_url,
            'method', 'POST',
            'headers', json_build_object('Content-Type', 'application/json'),
            'body', payload::text
        )::text
    );
    
    RETURN NEW;
END;
\$\$ LANGUAGE plpgsql;

-- Удаляем старый триггер если существует
DROP TRIGGER IF EXISTS hwid_device_http_webhook_trigger ON hwid_user_devices;

-- Создаем новый триггер
CREATE TRIGGER hwid_device_http_webhook_trigger
    AFTER INSERT ON hwid_user_devices
    FOR EACH ROW
    EXECUTE FUNCTION notify_hwid_device_http();

-- Проверяем что триггер создан
\\echo 'Checking trigger status...'
SELECT 
    trigger_name,
    event_manipulation,
    event_object_table,
    action_statement
FROM information_schema.triggers 
WHERE trigger_name = 'hwid_device_http_webhook_trigger';

\\echo 'HWID HTTP Webhook trigger created successfully!'
\\echo 'Webhook URL: $WEBHOOK_URL'
\\echo 'New HWID devices will trigger HTTP POST requests to your Telegram bot.'
EOF

# Выполняем SQL команды
if command -v docker &> /dev/null && docker ps | grep -q remnawave-db; then
    print_status "Подключаемся к PostgreSQL через Docker..."
    docker exec -i remnawave-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < setup_hwid_trigger.sql
    print_status "✅ PostgreSQL триггер создан успешно"
else
    print_warning "Docker контейнер remnawave-db не найден"
    print_warning "Пожалуйста, выполните команды из файла setup_hwid_trigger.sql вручную"
fi

# Очищаем временный файл
rm -f setup_hwid_trigger.sql

# 8. Установка и запуск systemd сервиса
print_status "Устанавливаем и запускаем systemd сервис..."

cp hwid-webhook-bridge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable hwid-webhook-bridge.service
systemctl start hwid-webhook-bridge.service

# 9. Проверка статуса
print_status "Проверяем статус сервиса..."
sleep 3

if systemctl is-active --quiet hwid-webhook-bridge.service; then
    print_status "✅ Сервис запущен успешно!"
else
    print_error "❌ Ошибка запуска сервиса"
    print_status "Логи сервиса:"
    journalctl -u hwid-webhook-bridge.service -n 20 --no-pager
fi

# 10. Финальная информация
echo ""
echo "🎉 Установка завершена!"
echo "========================"
echo ""
echo "📋 Созданы файлы:"
echo "   • /opt/remnawave/hwid_webhook_bridge.py - основной скрипт"
echo "   • /etc/systemd/system/hwid-webhook-bridge.service - systemd сервис"
echo ""
echo "🔧 Webhook настроен на: $WEBHOOK_URL"
echo ""
echo "📊 Полезные команды:"
echo "   • Статус сервиса:  systemctl status hwid-webhook-bridge"
echo "   • Логи в реальном времени: journalctl -u hwid-webhook-bridge -f"
echo "   • Перезапуск:      systemctl restart hwid-webhook-bridge"
echo "   • Остановка:       systemctl stop hwid-webhook-bridge"
echo ""
echo "📄 Логи также записываются в: /var/log/hwid_webhook_bridge.log"
echo ""
echo ""
print_status "Готово! 🚀"