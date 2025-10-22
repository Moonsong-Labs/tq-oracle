"""Price validators registry."""

from tq_oracle.adapters.price_validators.chainlink import ChainlinkValidator
from tq_oracle.adapters.price_validators.positive_prices import (
    PositivePricesValidator,
)

PRICE_VALIDATORS = [
    PositivePricesValidator,
    ChainlinkValidator,
]
