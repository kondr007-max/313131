"""
Настройки модуля Legal Policy
Все основные параметры модуля можно настроить в этом файле
"""

class LegalPolicySettings:
    """Класс настроек модуля правовых документов"""
    # Включение/выключение модуля
    ENABLED = True
    # URL пользовательского соглашения
    TERMS_OF_SERVICE_URL = "https://telegra.ph/1-Pravila-ispolzovaniya-servisa-AXIOME-VPN-BOT-02-04"
    
    # URL политики конфиденциальности  
    PRIVACY_POLICY_URL = "https://telegra.ph/1-Pravila-ispolzovaniya-servisa-AXIOME-VPN-BOT-02-04"
    
    # ========== НАСТРОЙКИ КНОПОК ==========
    
    # Текст кнопки пользовательского соглашения
    TERMS_BUTTON_TEXT = "соглашение"
    
    # Текст кнопки политики конфиденциальности
    PRIVACY_BUTTON_TEXT = "🔒 Политика"
    
    # ========== НАСТРОЙКИ ВЕБА И МИНИ-ПРИЛОЖЕНИЙ ==========
    
    # Включение WebApp кнопок (будут открывать ссылки в мини-приложении вместо браузера)
    USE_WEBAPP_BUTTONS = False
    
    # URL для WebApp пользовательского соглашения (если USE_WEBAPP_BUTTONS = True)
    # Если пусто, будет использоваться TERMS_OF_SERVICE_URL
    TERMS_WEBAPP_URL = "https://telegra.ph/1-Pravila-ispolzovaniya-servisa-AXIOME-VPN-BOT-02-04"
    
    # URL для WebApp политики конфиденциальности (если USE_WEBAPP_BUTTONS = True)
    # Если пусто, будет использоваться PRIVACY_POLICY_URL
    PRIVACY_WEBAPP_URL = "https://telegra.ph/1-Pravila-ispolzovaniya-servisa-AXIOME-VPN-BOT-02-04"
    
    # ========== ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ==========
    
    # Позиция кнопок в меню ("top" - вверху, "bottom" - внизу от других кнопок)
    BUTTONS_POSITION = "top"
    
    # Добавлять ли кнопки в одну строку (True) или в разные строки (False)
    BUTTONS_INLINE = True
    
    # ========== ВАЛИДАЦИЯ НАСТРОЕК ==========
    
    @classmethod
    def validate(cls):
        """Валидация настроек модуля"""
        errors = []
        
        # Проверяем обязательные URL если модуль включен
        if cls.ENABLED:
            if not cls.TERMS_OF_SERVICE_URL:
                errors.append("TERMS_OF_SERVICE_URL не может быть пустым при включенном модуле")
            
            if not cls.PRIVACY_POLICY_URL:
                errors.append("PRIVACY_POLICY_URL не может быть пустым при включенном модуле")
            
            # Проверяем валидность URL
            for url_name, url_value in [
                ("TERMS_OF_SERVICE_URL", cls.TERMS_OF_SERVICE_URL),
                ("PRIVACY_POLICY_URL", cls.PRIVACY_POLICY_URL),
                ("TERMS_WEBAPP_URL", cls.TERMS_WEBAPP_URL),
                ("PRIVACY_WEBAPP_URL", cls.PRIVACY_WEBAPP_URL)
            ]:
                if url_value and not (url_value.startswith('http://') or url_value.startswith('https://')):
                    errors.append(f"{url_name} должен начинаться с http:// или https://")
            
            # Проверяем тексты кнопок
            if not cls.TERMS_BUTTON_TEXT.strip():
                errors.append("TERMS_BUTTON_TEXT не может быть пустым")
            
            if not cls.PRIVACY_BUTTON_TEXT.strip():
                errors.append("PRIVACY_BUTTON_TEXT не может быть пустым")
            
            # Проверяем позицию кнопок
            if cls.BUTTONS_POSITION not in ["top", "bottom"]:
                errors.append("BUTTONS_POSITION должен быть 'top' или 'bottom'")
        
        if errors:
            raise ValueError(f"Ошибки конфигурации Legal Policy модуля:\n" + "\n".join(f"- {error}" for error in errors))
        
        return True
    
    @classmethod
    def get_effective_webapp_urls(cls):
        """Получить эффективные WebApp URL (с fallback на обычные URL)"""
        terms_webapp = cls.TERMS_WEBAPP_URL if cls.TERMS_WEBAPP_URL else cls.TERMS_OF_SERVICE_URL
        privacy_webapp = cls.PRIVACY_WEBAPP_URL if cls.PRIVACY_WEBAPP_URL else cls.PRIVACY_POLICY_URL
        
        return terms_webapp, privacy_webapp
