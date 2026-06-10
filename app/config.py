from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    bot_owner_id: int

    tg_api_id: int
    tg_api_hash: str
    tgapi_port: int = 8081
    tgapi_dir: str = "/var/lib/telegram-bot-api"

    ssh_user: str
    ssh_host: str
    ssh_port: int = 22
    socks_port: int = 1080
    cf_tunnel_host: str = ""

    save_path: str = "/app/saved"
    data_path: str = "/app/data"
    ssh_key_path: str = "/app/data/ssh"

    web_port: int = 8080
    admin_password: str
    session_secret: str = ""

    log_level: str = "INFO"
    timezone: str = "Asia/Shanghai"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
