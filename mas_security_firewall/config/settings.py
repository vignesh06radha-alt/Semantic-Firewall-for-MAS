from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GEMINI_API_KEY_ATLAS: str = ""
    GEMINI_API_KEY_BOHR: str = ""
    GEMINI_API_KEY_CURIE: str = ""
    GEMINI_API_KEY_FARADAY: str = ""
    GEMINI_API_KEY_GAUSS: str = ""
    GEMINI_API_KEY_DENG: str = ""
    GEMINI_API_KEY_EDISON: str = ""
    GEMINI_API_KEY_FIREWALL: str = ""

    CLASSIFIER_BACKEND_URL: str = "http://127.0.0.1:8000/v1/chat/completions"
    CLASSIFIER_MODEL_NAME: str = "meta-llama/Llama-Guard-3-1B"
    FIREWALL_TIMEOUT_MS: int = 1500
    MAX_ALLOWED_HOPS: int = 6
    FAIL_CLOSED: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
