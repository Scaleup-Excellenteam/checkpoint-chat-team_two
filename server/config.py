from pydantic_settings import BaseSettings, SettingsConfigDict

# Responsible for loading and managing server configuration
class Settings(BaseSettings):
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8080
    
    # Chat Settings
    default_room: str = "lobby"
    max_clients: int = 50
    max_message_length: int = 1024
    
    # Security Features
    enable_dlp: bool = False
    enable_url_filtering: bool = False
    
    # File Paths
    dlp_config_path: str = "config/dlp_rules.json"
    url_reputation_path: str = "config/url_reputation.json"
    
    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Gemini API Configuration
    gemini_api_key: str = "YOUR_GEMINI_API_KEY_HERE"
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
    
    # Database Configuration
    database_url: str = "sqlite:///./chat.db"
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    
    # Environment
    environment: str = "development"
    debug: bool = False
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()