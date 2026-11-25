from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

class ProviderConfig(BaseModel):
    type: Literal["ollama", "openai_compatible", "mock"]
    base_url: str | None = None
    base_url_env: str | None = None   # read base URL from this env var instead
    api_key_env: str | None = None    # name of env var holding the API key
     # Mock-only settings (ignored by real providers)
    latency_ms: int = 0
    error_rate: float = 0.0
    error: str = "rate_limit"
    reply: str = "Hello from the mock provider."

class ModelRoute(BaseModel):
    provider: str   # key in `providers`
    model: str      # provider's real model ID
    input_price: float = 0.0
    output_price: float = 0.0

    def cost(self, input_tokens: int, output_tokens: int)-> float:
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1_000_000

class GatewayConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelRoute]

    # Catch typos at startup: every model must point to a defined provider
    @model_validator(mode="after")
    def check_providers_exist(self):
        for name, route in self.models.items():
            if route.provider not in self.providers:
                raise ValueError(f"model '{name}' uses unknown provider '{route.provider}'")
        return self

# Read the YAML file and validate it with the models above
def load_config(path: str = "config/models.yaml") -> GatewayConfig:
    data = yaml.safe_load(Path(path).read_text())
    return GatewayConfig(**data)
