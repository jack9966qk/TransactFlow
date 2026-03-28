
from typing import List
from ..base import Transaction
from ..process import (
    GroupedProcess,
    Process,
    groupedProcessWrapper,
)

"""
Complex categorization processes.

This module contains multi-step or context-dependent transaction processing
rules that go beyond simple matching such as:

- Internal transfer pairing (labelIfMatch with relatedTo)
- Fee splitting (splitTransactionFee)
- Refund/reimbursement application (applyRefundOrReimbursement)
"""


@groupedProcessWrapper(atomic=False)
def process() -> List[Process]:
    return []
