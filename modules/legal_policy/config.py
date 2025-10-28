"""
Конфигурация модуля Legal Policy
УСТАРЕЛО: Используйте settings.py для настройки модуля
Этот файл оставлен для обратной совместимости
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from logger import logger

# Загрузка переменных окружения из папки модуля (для обратной совместимости)
module_dir = Path(__file__).parent
load_dotenv(module_dir / '.env')

class LegalPolicyConfig:
    """
    Конфигурация модуля правовых документов
    ВАЖНО: Этот класс устарел, используйте settings.py для настройки
    """
    
    def __init__(self):
        logger.warning("[LegalPolicy] config.py устарел, используйте settings.py для настройки модуля")
    
    @classmethod
    def _load_from_settings(cls):
        """Загрузка настроек из settings.py с fallback на .env"""
        try:
            from .settings import LegalPolicySettings
            
            # Валидируем настройки
            LegalPolicySettings.validate()
            
            # Копируем настройки из settings.py
            cls.ENABLED = LegalPolicySettings.ENABLED
            cls.TERMS_OF_SERVICE_URL = LegalPolicySettings.TERMS_OF_SERVICE_URL
            cls.PRIVACY_POLICY_URL = LegalPolicySettings.PRIVACY_POLICY_URL
            cls.TERMS_BUTTON_TEXT = LegalPolicySettings.TERMS_BUTTON_TEXT
            cls.PRIVACY_BUTTON_TEXT = LegalPolicySettings.PRIVACY_BUTTON_TEXT
            cls.USE_WEBAPP_BUTTONS = LegalPolicySettings.USE_WEBAPP_BUTTONS
            cls.BUTTONS_POSITION = LegalPolicySettings.BUTTONS_POSITION
            cls.BUTTONS_INLINE = LegalPolicySettings.BUTTONS_INLINE
            
            # Получаем эффективные WebApp URL
            cls.TERMS_WEBAPP_URL, cls.PRIVACY_WEBAPP_URL = LegalPolicySettings.get_effective_webapp_urls()
            
            logger.info("[LegalPolicy] Настройки успешно загружены из settings.py")
            return True
            
        except ImportError:
            logger.warning("[LegalPolicy] settings.py не найден, используем .env файл")
            return False
        except Exception as e:
            logger.error(f"[LegalPolicy] Ошибка загрузки из settings.py: {e}")
            return False
    
    @classmethod
    def _load_from_env(cls):
        """Загрузка настроек из .env файла (fallback)"""
        cls.ENABLED = os.getenv('LEGAL_POLICY_ENABLED', 'true').lower() == 'true'
        cls.TERMS_OF_SERVICE_URL = os.getenv('TERMS_OF_SERVICE_URL', '')
        cls.PRIVACY_POLICY_URL = os.getenv('PRIVACY_POLICY_URL', '')
        cls.TERMS_BUTTON_TEXT = os.getenv('TERMS_BUTTON_TEXT', '📄 Пользовательское соглашение')
        cls.PRIVACY_BUTTON_TEXT = os.getenv('PRIVACY_BUTTON_TEXT', '🔒 Политика конфиденциальности')
        cls.USE_WEBAPP_BUTTONS = os.getenv('USE_WEBAPP_BUTTONS', 'false').lower() == 'true'
        cls.BUTTONS_POSITION = os.getenv('BUTTONS_POSITION', 'top')
        cls.BUTTONS_INLINE = os.getenv('BUTTONS_INLINE', 'false').lower() == 'true'
        cls.TERMS_WEBAPP_URL = cls.TERMS_OF_SERVICE_URL
        cls.PRIVACY_WEBAPP_URL = cls.PRIVACY_POLICY_URL
        
        logger.info("[LegalPolicy] Настройки загружены из .env файла")
    
    @classmethod
    def load_config(cls):
        """Загрузка конфигурации (приоритет: settings.py > .env)"""
        if not cls._load_from_settings():
            cls._load_from_env()
    
    @classmethod
    def validate(cls):
        """Валидация конфигурации"""
        if not hasattr(cls, 'ENABLED'):
            cls.load_config()
            
        if not cls.ENABLED:
            return True
            
        required_fields = [
            ('TERMS_OF_SERVICE_URL', cls.TERMS_OF_SERVICE_URL),
            ('PRIVACY_POLICY_URL', cls.PRIVACY_POLICY_URL),
        ]
        
        missing = []
        for field_name, value in required_fields:
            if not value:
                missing.append(field_name)
        
        if missing:
            raise ValueError(f"Missing required legal policy configuration: {', '.join(missing)}")
        
        return True

# Автоматическая загрузка конфигурации при импорте
LegalPolicyConfig.load_config()
