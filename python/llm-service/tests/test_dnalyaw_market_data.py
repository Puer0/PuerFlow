"""Tests for Dnalyaw Market Data API OpenAPI tool integration."""

import os
import pytest
import yaml
from unittest.mock import patch

from llm_service.tools.openapi_tool import OpenAPILoader


SPEC_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "config",
    "openapi_specs",
    "dnalyaw_market_data.yaml",
)


@pytest.fixture
def dnalyaw_spec():
    """Load the Dnalyaw Market Data OpenAPI spec."""
    with open(SPEC_PATH) as f:
        return yaml.safe_load(f)


def _make_loader(spec, **kwargs):
    """Helper to create a loader with common defaults."""
    defaults = dict(
        name="dnalyaw_market_data",
        spec=spec,
        auth_type="api_key",
        auth_config={
            "api_key_name": "x-api-key",
            "api_key_location": "header",
            "api_key_value": "test-key",
        },
        category="data",
        base_cost_per_use=0.0,
    )
    defaults.update(kwargs)
    return OpenAPILoader(**defaults)


class TestDnalyawMarketDataSpec:
    """Test that the OpenAPI spec loads and generates correct tools."""

    @patch.dict(os.environ, {"OPENAPI_ALLOWED_DOMAINS": "*"})
    def test_spec_loads_single_operation(self, dnalyaw_spec):
        """Spec should parse and produce 1 operation (getStockBars only)."""
        loader = _make_loader(dnalyaw_spec)
        assert len(loader.operations) == 1

    @patch.dict(os.environ, {"OPENAPI_ALLOWED_DOMAINS": "*"})
    def test_spec_generates_tool_class(self, dnalyaw_spec):
        """Should produce a single getStockBars tool."""
        loader = _make_loader(dnalyaw_spec)
        tools = loader.generate_tools()
        assert len(tools) == 1
        meta = tools[0]()._get_metadata()
        assert meta.name == "getStockBars"

    @patch.dict(os.environ, {"OPENAPI_ALLOWED_DOMAINS": "*"})
    def test_get_stock_bars_params(self, dnalyaw_spec):
        """getStockBars should have symbol + exchange (required), plus optional params including limit and cursor."""
        loader = _make_loader(dnalyaw_spec)
        tools = loader.generate_tools()
        instance = tools[0]()
        params = instance._get_parameters()
        param_names = {p.name for p in params}
        assert {"symbol", "exchange", "interval", "range", "start", "end", "limit", "cursor"} == param_names
        for name in ["symbol", "exchange"]:
            p = next(p for p in params if p.name == name)
            assert p.required is True

    @patch.dict(os.environ, {"OPENAPI_ALLOWED_DOMAINS": "*"})
    def test_tool_metadata_category(self, dnalyaw_spec):
        """Tool should have category 'data' and cost 0.0."""
        loader = _make_loader(dnalyaw_spec)
        tools = loader.generate_tools()
        meta = tools[0]()._get_metadata()
        assert meta.category == "data"
        assert meta.cost_per_use == 0.0

    @patch.dict(os.environ, {"OPENAPI_ALLOWED_DOMAINS": "*"})
    def test_auth_headers_built(self, dnalyaw_spec):
        """API key auth should produce x-api-key header."""
        loader = _make_loader(
            dnalyaw_spec,
            auth_config={
                "api_key_name": "x-api-key",
                "api_key_location": "header",
                "api_key_value": "test-key-123",
            },
        )
        headers = loader._build_auth_headers()
        assert headers.get("x-api-key") == "test-key-123"
