"""Check adapters registry."""

from tq_oracle.adapters.check_adapters.active_submit_report_proposal_check import (
    ActiveSubmitReportProposalCheck,
)

from tq_oracle.adapters.check_adapters.safe_state import SafeStateAdapter
from tq_oracle.adapters.check_adapters.timeout_check import TimeoutCheckAdapter

CHECK_ADAPTERS = [
    SafeStateAdapter,
    ActiveSubmitReportProposalCheck,
    TimeoutCheckAdapter,
]
