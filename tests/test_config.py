import pytest
from pydantic import ValidationError

from app.config import GatewayConfig, ModelRoute, load_config


def test_cost_per_million_tokens():
    route = ModelRoute(provider="p", model="m", input_price=1.0, 
                       output_price=2.0)

    assert route.cost(1_000_000, 0) == 1.0
    assert route.cost(0, 1_000_000) == 2.0
    assert route.cost(5, 5) == pytest.approx(0.000015)

def test_free_model_costs_nothing():
    assert ModelRoute(provider="p", model="m").cost(1000, 1000) == 0

def test_unknown_provider_is_rejected():
    with pytest.raises(ValidationError, match="unknown provider"):
        GatewayConfig(
            providers={},
            models={"x":{"provider":"missing", "model":"m"}}
        )

def test_load_config_from_yaml(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(
        """
providers:
  mock:
    type: mock
models:
  mock:
    provider: mock
    model: mock-model
"""
    )
    config = load_config(str(path))
    assert config.providers["mock"].type == "mock"
    assert config.models["mock"].model == "mock-model"

