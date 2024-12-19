from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    USE_PROXY_FROM_FILE: bool = False

    REF_ID: str = "DTGYWCIWEZSAGUB"
    ENABLE_CHANNEL_SUBSCRIPTIONS: bool = False
    START_DELAY: tuple = (0, 300)
    TASK_COMPLETION_DELAY: tuple = (5, 10)
    VERIFY_CHECK_ATTEMPTS: int = 10
    VERIFY_CHECK_DELAY: tuple = (3, 5)
    ACTION_DELAY: tuple = (2, 4)

    REQUEST_TIMEOUT: tuple = (30, 60)
    RETRY_DELAY: tuple = (3, 10)
    MAX_RETRIES: int = 5
    
    AUTO_UPDATE: bool = True
    CHECK_UPDATE_INTERVAL: int = 300

    SLEEP_TIME: tuple = (3600, 7200)

    BASE_URL: str = "https://nutsfarm.crypton.xyz"
    API_VERSION: str = "v1"

    LOGGING_LEVEL: str = "INFO"
    ENABLE_RICH_LOGGING: bool = True
    LOG_USER_AGENT: bool = True
    LOG_PROXY: bool = True
    LOG_PROXY_CHECK: bool = False

    @property
    def API_URL(self) -> str:
        return f"{self.BASE_URL}/api/{self.API_VERSION}"


settings = Settings()

