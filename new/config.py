from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    GUARD_MODEL: str = "llama-guard3:8b"
    # Measured on this machine: gemma4:26b took ~275s for a single Policy
    # Evaluator call -- a 200-item x 3-config sweep (~600 such calls) would
    # take 40+ hours. llama3.2:3b answers the same prompt in ~10s, which is
    # what actually makes a real end-to-end sweep practical. Override via
    # .env if you have the GPU budget for something larger.
    AGENT_MODEL: str = "llama3.2:3b"

    FIREWALL_TIMEOUT_MS: int = 8000
    AGENT_TIMEOUT_MS: int = 120000

    # Hard cycle limit (spec: "iteration_count <= 4") -- caps DoS-loop
    # exhaustion if an injected payload convinces Policy Evaluator to keep
    # requesting re-evaluation. See graph.py / agents/enforcement.py.
    MAX_ITERATIONS: int = 4

    # Fast local heuristics standing in for real Ollama calls, so the whole
    # pipeline can be wiring-tested for free. Independent toggles: you can
    # mock the agents while hitting the real guard model, or vice versa.
    MOCK_AGENTS: bool = False
    MOCK_FIREWALL: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
