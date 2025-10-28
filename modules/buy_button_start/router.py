from aiogram import Router
from aiogram.types import InlineKeyboardButton

from hooks.hooks import register_hook
from logger import logger


router = Router(name="buy_button_start")


async def _start_menu_buy_button(chat_id: int, session, **kwargs):
    """
    Добавляет кнопку "Купить подписку" в стартовое меню.
    
    Логика:
    - Если есть пробный доступ (trial_status == 0) - не показываем кнопку (показывается стандартная "Пробный доступ")
    - Если нет пробного доступа (trial_status != 0) - показываем кнопку "Купить подписку" в самом верху
    """
    try:
        from database import get_trial

        trial_status = await get_trial(session, chat_id)
        
        # Если есть пробный доступ (trial_status == 0), не показываем кнопку
        # Стандартная кнопка "Пробный доступ" уже будет показана
        if trial_status == 0:
            return None
            
        # Если нет пробного доступа, показываем кнопку "Купить подписку" в самом верху
        return {"insert_at": 0, "button": InlineKeyboardButton(text="🔌 Купить подписку", callback_data="create_key")}
        
    except Exception as e:
        try:
            logger.error(f"[buy_button_start] Failed to build start menu button: {e}")
        except Exception:
            pass
        return None


register_hook("start_menu", _start_menu_buy_button)
