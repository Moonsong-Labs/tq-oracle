"""Price validators registry."""

from tq_oracle.adapters.price_validators.chainlink import ChainlinkValidator
from tq_oracle.adapters.price_validators.pyth import PythValidator

PRICE_VALIDATORS = [
    ChainlinkValidator,
    PythValidator,
]
