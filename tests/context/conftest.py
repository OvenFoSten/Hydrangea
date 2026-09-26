from __future__ import annotations

import pytest
from hypothesis import settings

from hydrangea.gateway import GatewayType

from .helpers import Harness


settings.register_profile("coop", deadline=None, derandomize=True, database=None)
settings.load_profile("coop")


@pytest.fixture(params=[GatewayType.gemini, GatewayType.openai], ids=["gemini", "openai"])
def gateway(request: pytest.FixtureRequest) -> GatewayType:
    return request.param


@pytest.fixture
def h(gateway: GatewayType) -> Harness:
    return Harness(gateway)
