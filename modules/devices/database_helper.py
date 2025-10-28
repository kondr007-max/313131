"""
Database helper functions for devices module
"""

from logger import logger
from database import async_session_maker
from database.models import Key
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


async def get_key_by_client_id(client_id: str):
    """
    Получает информацию о ключе по client_id
    
    Args:
        client_id (str): UUID клиента из hwid_user_devices.user_uuid = keys.client_id
        
    Returns:
        dict: Словарь с информацией о ключе или None
    """
    try:
        async with async_session_maker() as session:
            from sqlalchemy import select
            from database.models import Key
            
            # Ищем ключ по client_id в таблице keys бота
            result = await session.execute(
                select(Key).where(Key.client_id == client_id)
            )
            
            key = result.scalar_one_or_none()
            if key:
                return {
                    'id': key.client_id,
                    'tg_id': key.tg_id, 
                    'key_name': key.email or key.alias or 'Unknown',
                    'expired_at': key.expiry_time,
                    'days': None, 
                    'active': not key.is_frozen
                }
            else:
                logger.warning(f"[devices] Ключ с client_id {client_id} не найден в базе бота")
                return None
                
    except Exception as e:
        logger.error(f"[devices] Ошибка получения ключа по client_id {client_id}: {e}", exc_info=True)
        return None


async def get_user_keys_by_client_id(client_id: str):
    """
    Получает все ключи пользователя по client_id
    
    Args:
        client_id (str): UUID клиента
        
    Returns:
        list: Список словарей с информацией о ключах
    """
    try:
        key_info = await get_key_by_client_id(client_id)
        return [key_info] if key_info else []
            
    except Exception as e:
        logger.error(f"[devices] Ошибка получения ключей по client_id {client_id}: {e}", exc_info=True)
        return []