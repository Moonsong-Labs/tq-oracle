"""Price validators registry."""

from tq_oracle.adapters.price_validators.chainlink_last_look import (
    ChainLinkLastLookValidator,
)

PRICE_VALIDATORS = [
    ChainLinkLastLookValidator,
]
