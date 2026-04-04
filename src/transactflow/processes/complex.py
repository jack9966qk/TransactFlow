from typing import List
from ..process import (
    LazyGroupedProcess,
    Process,
)
from ..userConfig import forceReadUserConfig

"""
Complex categorization processes.

This module contains multi-step or context-dependent transaction processing
rules that go beyond simple matching such as:

- Internal transfer pairing (labelIfMatch with relatedTo)
- Fee splitting (splitTransactionFee)
- Refund/reimbursement application (applyRefundOrReimbursement)

All processes are user-supplied via ProcessConfig.complexProcesses.
"""


def _buildComplexProcesses() -> List[Process]:
    config = forceReadUserConfig().processes
    if config is None: return []
    userSupplied = config.complexProcess
    return [] if userSupplied is None else [userSupplied]


process = LazyGroupedProcess(label="Complex categorization", buildProcesses=_buildComplexProcesses)
