from aiogram import Router
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from hooks.hooks import register_hook
from logger import logger


router = Router(name="backup_bot_pin_module")


async def start_link_hook(message=None, state=None, session=None, user_data=None, part: str = "", **kwargs):
    try:
        from .settings import (
            ENABLE, BUTTON_TEXT, BACKUP_BOT_URL, PIN_TEXT, 
            SEARCH_KEYWORDS, UNPIN_PREVIOUS, DISABLE_NOTIFICATION
        )
        if not ENABLE:
            return None

        try:
            chat_info = await message.bot.get_chat(message.chat.id)
            pinned_message = chat_info.pinned_message
            
            if pinned_message and pinned_message.text:
                message_text_lower = pinned_message.text.lower()
                has_backup_keywords = any(keyword.lower() in message_text_lower for keyword in SEARCH_KEYWORDS)
                
                if has_backup_keywords:
                    logger.info(f"[BackupPin] В чате {message.chat.id} уже есть закрепленное сообщение о запасном боте")
                    return None
                    
        except Exception as e:
            logger.warning(f"[BackupPin] Не удалось проверить закрепленные сообщения: {e}")

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text=BUTTON_TEXT, url=BACKUP_BOT_URL))

        sent = await message.answer(PIN_TEXT, reply_markup=kb.as_markup())
        
        try:
            if UNPIN_PREVIOUS:
                await message.bot.unpin_all_chat_messages(message.chat.id)
                logger.info(f"[BackupPin] Предыдущие сообщения откреплены в чате {message.chat.id}")
            
            await message.bot.pin_chat_message(
                message.chat.id, 
                sent.message_id, 
                disable_notification=DISABLE_NOTIFICATION
            )
            logger.info(f"[BackupPin] Сообщение о запасном боте закреплено в чате {message.chat.id}")
            
        except Exception as e:
            logger.warning(f"[BackupPin] Не удалось закрепить сообщение: {e}")
            
    except Exception as e:
        logger.error(f"[BackupPin] Ошибка в start_link_hook: {e}")
    return None


register_hook("start_link", start_link_hook)
logger.info("[BackupPin] Модуль инициализирован — закрепление запасного бота при первом взаимодействии")


