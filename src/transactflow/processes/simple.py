from typing import List
from ..base import Transaction
from ..process import (
    GroupedProcess,
    Process,
    funcProcess,
    groupedProcessWrapper,
    labelIfMatch,
    labelGeneralExpenseDestination,
    labelNotReallyIncomeIfUncategorizedIncome,
    labelSalaryIncome,
    matching,
    relabelShoppingAsDaily,
    relabelShoppingAsMajor,
)

"""
Simple categorization processes.
"""


@groupedProcessWrapper(atomic=False)
def process() -> List[Process]:
    return [
        # labelSalaryIncome requires relatedTo=EMPLOYER to be set by user-specific rules.
        # Add it back once you have employer labelling configured.
        labelGeneralExpenseDestination,
        labelNotReallyIncomeIfUncategorizedIncome,
        # relabelShoppingAsDaily and relabelShoppingAsMajor require SHOPPING category
        # transactions, which come from user-specific rules. Add them back once configured.
    ]
