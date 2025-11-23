"""Price validators registry."""

from tq_oracle.adapters.price_validators.pyth import PythValidator

# Check is removed until a triangulation process is implemented
PRICE_VALIDATORS = [
    PythValidator,
]
