import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from config import SUPPORT_CHAT_URL, USERNAME_BOT, WEBHOOK_HOST, PROJECT_NAME, DATABASE_URL, HAPP_CRYPTOLINK, SUPERNODE
from database.models import Key, Server
import re

from panels._3xui import get_vless_link_for_client, get_xui_instance


def extract_host(api_url: str) -> str:
    match = re.match(r"(https?://)?([^:/]+)", api_url)
    return match.group(2) if match else api_url

from .settings import (
    APPS_ENABLED, DEEPLINKS, APP_LINKS, BUTTONS_ENABLED, CURRENT_THEME, LANGUAGE_MODE, FALLBACK_LANGUAGE, BASE_PATH,
    RATE_LIMIT_ENABLED, RATE_LIMIT_REQUESTS, RATE_LIMIT_PERIOD, RATE_LIMIT_BLOCK_TIME, HAPTIC_ENABLED, VLESS_SELECTOR_ENABLED
)

if not BASE_PATH.endswith('/'):
    BASE_PATH = BASE_PATH + '/'
from .texts import STATIC_TEXTS, DINAMIC_TEXTS

rate_limit_storage = {
    "requests": {},
    "blocked": {}
}

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"

def check_rate_limit(ip: str) -> bool:
    if not RATE_LIMIT_ENABLED:
        return True
    
    current_time = time.time()
    
    if ip in rate_limit_storage["blocked"]:
        block_until = rate_limit_storage["blocked"][ip]
        if current_time < block_until:
            return False
        else:
            del rate_limit_storage["blocked"][ip]
    
    if ip not in rate_limit_storage["requests"]:
        rate_limit_storage["requests"][ip] = []
    
    rate_limit_storage["requests"][ip] = [
        req_time for req_time in rate_limit_storage["requests"][ip]
        if current_time - req_time < RATE_LIMIT_PERIOD
    ]
    
    if len(rate_limit_storage["requests"][ip]) >= RATE_LIMIT_REQUESTS:
        rate_limit_storage["blocked"][ip] = current_time + RATE_LIMIT_BLOCK_TIME
        logging.warning(f"[Subscription Page] IP {ip} blocked for {RATE_LIMIT_BLOCK_TIME}s")
        return False
    
    rate_limit_storage["requests"][ip].append(current_time)
    return True


_module_engine = None
_module_session_maker = None

def get_module_session_maker():
    global _module_engine, _module_session_maker
    if _module_session_maker is None:
        _module_engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            future=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=15
        )
        _module_session_maker = async_sessionmaker(
            bind=_module_engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
    return _module_session_maker

def get_all_texts(language="ru"):
    texts = {}
    texts.update(STATIC_TEXTS.get(language, STATIC_TEXTS["ru"]))
    texts.update(DINAMIC_TEXTS.get(language, DINAMIC_TEXTS["ru"]))
    return texts

def create_api_routes(app, module_path):

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[WEBHOOK_HOST],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors 'self' https://web.telegram.org https://telegram.org; "
            "script-src 'self' 'unsafe-inline' https://telegram.org https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.tailwindcss.com"
        )
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        return response

    @app.get(f"{BASE_PATH}", response_class=HTMLResponse)
    async def device_connector_index():
        html_path = os.path.join(module_path, "static", "index.html")
        version_path = os.path.join(module_path, "VERSION")

        version = "1.0.0"
        if os.path.exists(version_path):
            with open(version_path, encoding="utf-8") as f:
                version = f.read().strip()

        if os.path.exists(html_path):
            with open(html_path, encoding="utf-8") as f:
                content = f.read()

            content = content.replace("{{PROJECT_NAME}}", PROJECT_NAME)
            content = content.replace("{{WEBHOOK_HOST}}", WEBHOOK_HOST)
            content = content.replace("{{SUPPORT_CHAT_URL}}", SUPPORT_CHAT_URL)
            content = content.replace("{{USERNAME_BOT}}", USERNAME_BOT)
            content = content.replace("{{BASE_PATH}}", BASE_PATH)
            content = content.replace("{{VERSION}}", version)

            return HTMLResponse(content=content)

        return HTMLResponse(content=f"<h1>Подключение устройства</h1><p>Модуль xui_subpage активирован для {PROJECT_NAME}</p>")

    @app.get(f"{BASE_PATH}api/sub")
    async def get_sub(request: Request, key_name=Query(None)):

        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again in 5 minutes."
            )

        if not key_name:
            raise HTTPException(status_code=400, detail="Required key_name parameter")

        try:
            session_maker = get_module_session_maker()
            async with session_maker() as session:
                query = select(Key).where(
                    Key.email == key_name,
                    Key.is_frozen == False
                ).limit(1)

                result = await session.execute(query)
                row = result.scalar_one_or_none()

                if not row:
                    raise HTTPException(status_code=404, detail="Subscription not found")
                expiry_iso = datetime.fromtimestamp(row.expiry_time / 1000, timezone.utc).isoformat()
                remnawave_link = getattr(row, "remnawave_link", None)

                if HAPP_CRYPTOLINK and remnawave_link:
                    primary_link = remnawave_link
                    is_crypto_link = True
                else:
                    primary_link = row.key or remnawave_link
                    is_crypto_link = False

                return {
                    "key": row.key,
                    "expiry": expiry_iso,
                    "link": primary_link,
                    "email": getattr(row, "email", ""),
                    "is_crypto_link": is_crypto_link,
                    "remnawave_link": remnawave_link if HAPP_CRYPTOLINK else None,
                }

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"[Subscription Page] Database error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get(f"{BASE_PATH}api/country-links")
    async def get_country_links(request: Request, key_name: str = Query(None)):

        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again in 5 minutes."
            )

        if not key_name:
            raise HTTPException(status_code=400, detail="Required key_name parameter")

        try:
            session_maker = get_module_session_maker()
            async with session_maker() as session:
                key_stmt = select(Key).where(
                    Key.email == key_name,
                    Key.is_frozen == False
                ).limit(1)

                key_result = await session.execute(key_stmt)
                key_row = key_result.scalar_one_or_none()

                if not key_row:
                    raise HTTPException(status_code=404, detail="Subscription not found")

                server_identifier = key_row.server_id
                base_server = None

                if server_identifier:
                    base_stmt = (
                        select(Server)
                        .where(
                            or_(
                                Server.cluster_name == server_identifier,
                                Server.server_name == server_identifier,
                            )
                        )
                        .limit(1)
                    )
                    base_server = (await session.execute(base_stmt)).scalar_one_or_none()

                    if not base_server:
                        by_group_stmt = (
                            select(Server)
                            .where(Server.tariff_group == server_identifier)
                            .limit(1)
                        )
                        base_server = (await session.execute(by_group_stmt)).scalar_one_or_none()

                tariff_group = base_server.tariff_group if base_server else None
                cluster_name = base_server.cluster_name if base_server else None

                if not cluster_name and server_identifier:
                    cluster_name = server_identifier

                if not tariff_group and server_identifier:
                    tg_stmt = (
                        select(Server.tariff_group)
                        .where(Server.cluster_name == server_identifier)
                        .limit(1)
                    )
                    tariff_group = (await session.execute(tg_stmt)).scalar_one_or_none()

                filters = [Server.enabled.is_(True)]
                if tariff_group:
                    filters.append(Server.tariff_group == tariff_group)
                elif cluster_name:
                    filters.append(Server.cluster_name == cluster_name)
                else:
                    return {"countries": []}

                servers_stmt = select(Server).where(*filters)
                servers_result = await session.execute(servers_stmt)
                servers = [srv for srv in servers_result.scalars().all() if (srv.panel_type or '').lower() == '3x-ui']

                if not servers:
                    return {"countries": []}

                async def build_country_entry(server: Server):
                    inbound_id = server.inbound_id
                    if not inbound_id or not server.api_url:
                        return None

                    login_email = f"{key_name}_{server.server_name.lower()}" if SUPERNODE and server.server_name else key_name

                    try:
                        xui = await get_xui_instance(server.api_url)
                        inbound = await xui.inbound.get_by_id(int(inbound_id))
                        if not inbound:
                            return None

                        country_name = getattr(inbound, 'remark', None) or server.server_name or 'Server'
                        host_source = server.subscription_url or server.api_url
                        host = extract_host(host_source)
                        port = getattr(inbound, 'port', None)
                        if not host or not port:
                            return None

                        link_remark = f"{country_name}-{key_name}"
                        link = await get_vless_link_for_client(
                            xui=xui,
                            inbound_id=int(inbound_id),
                            email=login_email,
                            external_host=host,
                            port=int(port),
                            remark=link_remark,
                        )
                        if not link:
                            return None

                        return {
                            "country": str(country_name),
                            "link": link,
                            "server_name": server.server_name,
                        }
                    except Exception as ex:
                        logging.warning(
                            f"[Subscription Page] Failed to build country link for {server.server_name}: {ex}"
                        )
                        return None

                tasks = [build_country_entry(server) for server in servers]
                raw_results = await asyncio.gather(*tasks, return_exceptions=True)

                countries = []
                for item in raw_results:
                    if isinstance(item, dict):
                        countries.append({"country": item["country"], "link": item["link"]})
                    elif isinstance(item, Exception):
                        logging.warning(f"[Subscription Page] country-links task error: {item}")

                if not countries:
                    return {"countries": []}

                countries.sort(key=lambda entry: entry["country"] or "")
                return {"countries": countries}

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"[Subscription Page] country-links error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post(f"{BASE_PATH}auth/start")
    async def auth_start():
        return JSONResponse(content={"status": "ok"})

    @app.get(f"{BASE_PATH}api/settings")
    async def get_settings():
        return JSONResponse(content={
                "project_name": PROJECT_NAME,
                "bot_username": USERNAME_BOT,
                "support_chat": SUPPORT_CHAT_URL,
                "webhook_host": WEBHOOK_HOST,
                "base_path": BASE_PATH,
                "color_theme": CURRENT_THEME,
                "language": {
                    "default_mode": LANGUAGE_MODE,
                    "fallback": FALLBACK_LANGUAGE
                },
                "apps": APPS_ENABLED,
                "deeplinks": DEEPLINKS,
                "app_links": APP_LINKS,
                "buttons": BUTTONS_ENABLED,
                "happ_cryptolink": HAPP_CRYPTOLINK,
                "haptic_enabled": HAPTIC_ENABLED,
                "vless_selector_enabled": VLESS_SELECTOR_ENABLED
            })

    @app.get(f"{BASE_PATH}health")
    async def health_check():
        try:
            session_maker = get_module_session_maker()
            async with session_maker() as session:
                await session.execute(select(1))
                db_status = "ok"
        except Exception:
            db_status = "unavailable"
        return JSONResponse(content={"status": "ok", "database": db_status, "module": "xui_subpage"})

    @app.get(f"{BASE_PATH}api/texts")
    async def get_texts(language: str = "ru"):
        texts = get_all_texts(language)
        return JSONResponse(content={"texts": texts, "language": language})

    @app.post(f"{BASE_PATH}api/tv")
    async def send_to_tv(request: Request):
        
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again in 5 minutes."
            )
        
        try:
            import httpx

            data = await request.json()
            code = data.get("code")
            subscription_data = data.get("data")

            if not code or not subscription_data:
                return JSONResponse(
                    content={"success": False, "error": "Missing code or data parameter"},
                    status_code=400
                )

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://check.happ.su/sendtv/{code}",
                    headers={"Content-Type": "application/json"},
                    json={"data": subscription_data}
                )

                response_text = response.text

                if response.status_code == 200:
                    return JSONResponse(
                        content={
                            "success": True,
                            "message": "Subscription sent successfully",
                            "response": response_text
                        }
                    )
                else:
                    return JSONResponse(
                        content={
                            "success": False,
                            "error": f"Happ API error: {response.status_code}",
                            "response": response_text
                        },
                        status_code=response.status_code
                    )

        except Exception as e:
            logging.error(f"[Subscription Page] Error sending to Happ API: {e}")
            return JSONResponse(
                content={"success": False, "error": str(e)},
                status_code=500
            )

    @app.get(f"{BASE_PATH}api/qr")
    async def get_qr_code(request: Request, key_name: str = Query(None)):
        
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again in 5 minutes."
            )
        
        if not key_name:
            raise HTTPException(status_code=400, detail="Required key_name parameter")
        
        try:
            import qrcode
            from io import BytesIO
            
            session_maker = get_module_session_maker()
            async with session_maker() as session:
                query = select(Key).where(
                    Key.email == key_name,
                    Key.is_frozen == False
                ).limit(1)
                
                result = await session.execute(query)
                row = result.scalar_one_or_none()
                
                if not row:
                    raise HTTPException(status_code=404, detail="Subscription not found")
                
                remnawave_link = getattr(row, "remnawave_link", None)
                
                if HAPP_CRYPTOLINK and remnawave_link:
                    qr_data = remnawave_link
                else:
                    qr_data = row.key or remnawave_link
                
                if not qr_data:
                    raise HTTPException(status_code=404, detail="No subscription link available")
                
                logging.info(f"[Subscription Page] Generating QR for key: {key_name}, data length: {len(qr_data)}")
                
                qr = qrcode.QRCode(version=1, box_size=10, border=1)
                qr.add_data(qr_data)
                qr.make(fit=True)
                
                img = qr.make_image(fill_color="black", back_color="white")
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                buffer.seek(0)
                
                return StreamingResponse(buffer, media_type="image/png")
        
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"[Subscription Page] QR code generation error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
