from typing import List
from ..base import Transaction
from ..process import (
    LazyGroupedProcess,
    Process,
    labelGeneralExpenseDestination,
    labelNotReallyIncomeIfUncategorizedIncome,
)
from ..userConfig import forceReadUserConfig

"""
Simple categorization processes.

Built-in rules (labelGeneralExpenseDestination, labelNotReallyIncomeIfUncategorizedIncome)
are always applied. User-supplied simpleProcesses from ProcessConfig are appended after.
"""


def _buildSimpleProcesses() -> List[Process]:
    userSupplied = forceReadUserConfig().processes.simpleProcess
    return [] if userSupplied is None else [userSupplied]

process = LazyGroupedProcess(label="Simple categorization", buildProcesses=_buildSimpleProcesses)
