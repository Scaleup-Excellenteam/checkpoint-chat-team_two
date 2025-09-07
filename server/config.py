from pydantic_settings import BaseSettings, SettingsConfigDict

# Responsible for loading and managing server configuration
class Settings(BaseSettings):
    host: str = "0.0.0.0"   # important for containers
    port: int = 8080
    default_room: str = "lobby"
    max_clients: int = 50
    max_message_length: int = 1024
    enable_dlp: bool = False
    enable_url_filtering: bool = False
    dlp_config_path: str = "config/dlp_rules.json"
    url_reputation_path: str = "config/url_reputation.json"
    log_level: str = "INFO"
    log_format: str = "json"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()