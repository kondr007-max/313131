import os
import threading
import uvicorn
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from hooks.hooks import register_hook
from .settings import MODULE_PORT, BASE_PATH, MODULE_ENABLED

def _disable_remnawave_webapp_flag():
    patched_modules = (
        "handlers.keys.key_mode.key_cluster_mode",
        "handlers.keys.key_mode.key_country_mode",
        "handlers.notifications.special_notifications",
    )

    try:
        import config

        config.REMNAWAVE_WEBAPP = False
        print("[Subscription Page] REMNAWAVE_WEBAPP переопределен на False")

        for module_path in patched_modules:
            try:
                module = __import__(module_path, fromlist=["REMNAWAVE_WEBAPP"])
                if hasattr(module, "REMNAWAVE_WEBAPP"):
                    setattr(module, "REMNAWAVE_WEBAPP", False)
                    logging.info(
                        "[Subscription Page] REMNAWAVE_WEBAPP отключен в %s",
                        module_path,
                    )
            except Exception as patch_error:
                logging.warning(
                    "[Subscription Page] Не удалось обновить REMNAWAVE_WEBAPP в %s: %s",
                    module_path,
                    patch_error,
                )
    except Exception as cfg_error:
        logging.error(
            "[Subscription Page] Ошибка при отключении REMNAWAVE_WEBAPP: %s",
            cfg_error,
        )


if MODULE_ENABLED:
    _disable_remnawave_webapp_flag()

if not BASE_PATH.endswith('/'):
    BASE_PATH = BASE_PATH + '/'
from .api import create_api_routes
from .telegram import create_telegram_router, profile_menu_hook, view_key_menu_hook, key_creation_complete_hook, zero_traffic_notification_hook

def get_version():
    version_file = os.path.join(os.path.dirname(__file__), "VERSION")
    try:
        with open(version_file, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1.0.0"

router = create_telegram_router()
MODULE_PATH = os.path.dirname(__file__)
STATIC_PATH = os.path.join(MODULE_PATH, "static")

app = FastAPI(title="3X-UI Subscription Page", version=get_version())
create_api_routes(app, MODULE_PATH)
if os.path.exists(STATIC_PATH):
    app.mount(f"{BASE_PATH}static", StaticFiles(directory=STATIC_PATH), name="static")

def run_fastapi_server():
    try:
        uvicorn.run(app, host="0.0.0.0", port=MODULE_PORT, log_level="warning", access_log=False)
    except Exception as e:
        logging.error(f"[Subscription Page] Ошибка запуска сервера: {e}")

server_thread = threading.Thread(target=run_fastapi_server, daemon=True)
server_thread.start()
register_hook("profile_menu", profile_menu_hook)
register_hook("view_key_menu", view_key_menu_hook)
register_hook("key_creation_complete", key_creation_complete_hook)
register_hook("zero_traffic_notification", zero_traffic_notification_hook)
print("[Subscription Page] Хуки зарегистрированы для замены кнопок")
