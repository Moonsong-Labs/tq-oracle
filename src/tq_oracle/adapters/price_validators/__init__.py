"""Price validators registry."""

from tq_oracle.adapters.price_validators.chainlink import ChainlinkValidator

PRICE_VALIDATORS = [
    ChainlinkValidator,
]
