"""Check adapters registry."""

from tq_oracle.adapters.check_adapters.cctp_bridge import CCTPBridgeAdapter
from tq_oracle.adapters.check_adapters.safe_state import SafeStateAdapter
from tq_oracle.adapters.check_adapters.timeout_check import TimeoutCheckAdapter

# TODO: Add DeBridge adapter when implemented
# from tq_oracle.adapters.check_adapters.debridge import DeBridgeAdapter

CHECK_ADAPTERS = [
    SafeStateAdapter,
    CCTPBridgeAdapter,
    TimeoutCheckAdapter,
    # DeBridgeAdapter,  # TODO: Implement DeBridge in-flight detection
]
