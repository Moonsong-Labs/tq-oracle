import pytest
from unittest.mock import MagicMock, patch
import time

from tq_oracle.adapters.price_validators.pyth import PythValidator
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.settings import OracleSettings, Network


@pytest.fixture
def config():
    return OracleSettings(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        vault_rpc="https://eth.drpc.org",
        network=Network.MAINNET,
        safe_address=None,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
        pyth_enabled=True,
        pyth_staleness_threshold=60,
        price_warning_tolerance_percentage=0.5,
        price_failure_tolerance_percentage=1.0,
        pyth_max_confidence_ratio=0.03,
    )


@pytest.fixture
def validator(config):
    return PythValidator(config)


@pytest.fixture
def eth_address(config):
    address = config.assets["ETH"]
    assert address is not None
    return address


@pytest.fixture
def usdc_address(config):
    address = config.assets["USDC"]
    assert address is not None
    return address


def _make_mock_response(payload: dict | list) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _default_discovery_payload() -> list[dict]:
    return [
        {
            "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
            "type": "derived",
            "attributes": {"base": "ETH", "quote_currency": "USD"},
        },
        {
            "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
            "type": "derived",
            "attributes": {"base": "USDC", "quote_currency": "USD"},
        },
    ]


def _patch_requests(mock_discovery: MagicMock, mock_price: MagicMock):
    def _mock(url: str, params=None, timeout=None):
        if url.endswith("/v2/price_feeds"):
            return mock_discovery
        return mock_price

    return _mock


def test_staleness_threshold(validator):
    """Test that staleness threshold is set correctly."""
    assert validator.pyth_adapter.staleness_threshold == 60


def test_deviation_thresholds(validator):
    """Test that deviation thresholds are set correctly."""
    assert validator.warning_tolerance == 0.5
    assert validator.failure_tolerance == 1.0


@pytest.mark.asyncio
async def test_validate_prices_disabled(config, eth_address, usdc_address):
    """Test that validation passes when Pyth is disabled."""
    config.pyth_enabled = False
    validator = PythValidator(config)

    price_data = PriceData(
        base_asset=eth_address,
        prices={usdc_address: 3000000000000000},
    )

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "disabled" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_prices_with_mocked_pyth(config, eth_address, usdc_address):
    """Test validation with mocked HTTP response."""
    validator = PythValidator(config)

    current_time = int(time.time())

    # Mock HTTP response
    mock_response_data = {
        "parsed": [
            {
                "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                "price": {
                    "price": "3000",
                    "expo": 0,
                    "conf": "10",
                    "publish_time": current_time,
                },
            },
            {
                "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                "price": {
                    "price": "1",
                    "expo": 0,
                    "conf": "1",
                    "publish_time": current_time,
                },
            },
        ]
    }

    mock_price_response = _make_mock_response(mock_response_data)
    mock_discovery_response = _make_mock_response(_default_discovery_payload())

    with patch(
        "requests.get",
        side_effect=_patch_requests(mock_discovery_response, mock_price_response),
    ):
        # Oracle price: USDC is ~1/3000 ETH (since ETH is $3000 and USDC is $1)
        price_data = PriceData(
            base_asset=eth_address,
            prices={usdc_address: int((1 / 3000) * 1e18)},
        )

        result = await validator.validate_prices(price_data)

        assert result.passed
        assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_prices_fails_on_excessive_deviation(
    config, eth_address, usdc_address
):
    """Test that validation fails when price deviation exceeds threshold."""
    validator = PythValidator(config)

    current_time = int(time.time())

    # Mock HTTP response
    mock_response_data = {
        "parsed": [
            {
                "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                "price": {
                    "price": "3000",
                    "expo": 0,
                    "conf": "10",
                    "publish_time": current_time,
                },
            },
            {
                "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                "price": {
                    "price": "1",
                    "expo": 0,
                    "conf": "1",
                    "publish_time": current_time,
                },
            },
        ]
    }

    mock_price_response = _make_mock_response(mock_response_data)
    mock_discovery_response = _make_mock_response(_default_discovery_payload())

    with patch(
        "requests.get",
        side_effect=_patch_requests(mock_discovery_response, mock_price_response),
    ):
        # Oracle price: Intentionally wrong - USDC price way off
        price_data = PriceData(
            base_asset=eth_address,
            prices={usdc_address: int((1 / 2000) * 1e18)},  # 50% deviation
        )

        result = await validator.validate_prices(price_data)

        assert not result.passed
        assert (
            "failure threshold" in result.message.lower()
            or "off" in result.message.lower()
        )


@pytest.mark.asyncio
async def test_validate_prices_handles_stale_eth_price(
    config, eth_address, usdc_address
):
    """Test that validation fails when ETH/USD price is stale."""
    validator = PythValidator(config)

    # Make the price stale (published 120 seconds ago, staleness threshold is 60s)
    stale_time = int(time.time()) - 120

    mock_response_data = {
        "parsed": [
            {
                "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                "price": {
                    "price": "3000",
                    "expo": 0,
                    "conf": "10",
                    "publish_time": stale_time,  # Stale!
                },
            },
        ]
    }

    mock_price_response = _make_mock_response(mock_response_data)
    mock_discovery_response = _make_mock_response(_default_discovery_payload())

    with patch(
        "requests.get",
        side_effect=_patch_requests(mock_discovery_response, mock_price_response),
    ):
        price_data = PriceData(
            base_asset=eth_address,
            prices={usdc_address: int((1 / 3000) * 1e18)},
        )

        result = await validator.validate_prices(price_data)

        assert not result.passed
        assert "stale" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_prices_handles_api_error(config, eth_address, usdc_address):
    """Test that validation handles API errors gracefully."""
    validator = PythValidator(config)

    # Mock an exception during the HTTP call
    with patch("requests.get", side_effect=Exception("API Error")):
        price_data = PriceData(
            base_asset=eth_address,
            prices={usdc_address: int((1 / 3000) * 1e18)},
        )

        result = await validator.validate_prices(price_data)

        assert not result.passed
        assert result.retry_recommended


@pytest.mark.asyncio
async def test_validate_prices_fails_on_missing_feed_when_flag_set(
    config, eth_address, usdc_address
):
    """Validator should fail when a feed is missing and fail_on_missing is enabled."""

    config.pyth_fail_on_missing_price = True
    validator = PythValidator(config)

    current_time = int(time.time())

    # Only ETH feed present in response; USDC feed missing
    mock_response_data = {
        "parsed": [
            {
                "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                "price": {
                    "price": "3000",
                    "expo": 0,
                    "conf": "10",
                    "publish_time": current_time,
                },
            }
        ]
    }

    mock_price_response = _make_mock_response(mock_response_data)
    mock_discovery_response = _make_mock_response(_default_discovery_payload())

    with patch(
        "requests.get",
        side_effect=_patch_requests(mock_discovery_response, mock_price_response),
    ):
        price_data = PriceData(
            base_asset=eth_address,
            prices={usdc_address: int((1 / 3000) * 1e18)},
        )

        result = await validator.validate_prices(price_data)

        assert not result.passed
        assert not result.retry_recommended
        assert "missing" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_prices_fails_on_stale_feed_when_flag_set(
    config, eth_address, usdc_address
):
    """Validator should fail when a feed is stale and fail_on_stale is enabled."""

    config.pyth_fail_on_stale_price = True
    validator = PythValidator(config)

    stale_time = int(time.time()) - 120
    current_time = int(time.time())

    mock_response_data = {
        "parsed": [
            {
                "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                "price": {
                    "price": "3000",
                    "expo": 0,
                    "conf": "10",
                    "publish_time": current_time,
                },
            },
            {
                "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                "price": {
                    "price": "1",
                    "expo": 0,
                    "conf": "1",
                    "publish_time": stale_time,
                },
            },
        ]
    }

    mock_price_response = _make_mock_response(mock_response_data)
    mock_discovery_response = _make_mock_response(_default_discovery_payload())

    with patch(
        "requests.get",
        side_effect=_patch_requests(mock_discovery_response, mock_price_response),
    ):
        price_data = PriceData(
            base_asset=eth_address,
            prices={usdc_address: int((1 / 3000) * 1e18)},
        )

        result = await validator.validate_prices(price_data)

        assert not result.passed
        assert result.retry_recommended
        assert "stale" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_prices_passes_with_empty_prices(validator, eth_address):
    """Test that validation passes with empty price data."""
    current_time = int(time.time())

    mock_response_data = {
        "parsed": [
            {
                "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                "price": {
                    "price": "3000",
                    "expo": 0,
                    "conf": "10",
                    "publish_time": current_time,
                },
            },
        ]
    }

    mock_price_response = _make_mock_response(mock_response_data)
    mock_discovery_response = _make_mock_response(
        [
            {
                "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                "type": "derived",
                "attributes": {"base": "ETH", "quote_currency": "USD"},
            }
        ]
    )

    with patch(
        "requests.get",
        side_effect=_patch_requests(mock_discovery_response, mock_price_response),
    ):
        price_data = PriceData(base_asset=eth_address, prices={})

        result = await validator.validate_prices(price_data)

        assert result.passed
        assert "within acceptable deviation" in result.message.lower()
