import os

from app.config import GatewayConfig, ProviderConfig
from app.providers.base import Provider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compat import OpenAICompatibleProvider
from app.providers.mock import MockProvider



def _base_url(cfg: ProviderConfig) -> str:
    return cfg.base_url or os.environ[cfg.base_url_env]



def build_providers(config: GatewayConfig) -> dict[str, Provider]:
    providers: dict[str, Provider] = {}
    for name, cfg in config.providers.items():
        if cfg.type == "ollama":
            providers[name] = OllamaProvider(_base_url(cfg))
        elif cfg.type == "openai_compatible":
            providers[name] = OpenAICompatibleProvider(
                name, _base_url(cfg), os.environ[cfg.api_key_env]
            )
        elif cfg.type == "mock":
            providers[name] = MockProvider(
                name=name,
                latency_ms=cfg.latency_ms,
                error_rate=cfg.error_rate,
                error=cfg.error,
                reply=cfg.reply,
            )
    return providers