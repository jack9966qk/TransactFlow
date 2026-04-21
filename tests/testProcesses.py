from typing import Callable

import transactflow.processes.importer
import transactflow.processes.payslipIncome
import transactflow.processes.runAll
from transactflow.analysis import totalAccountBalance
from transactflow.base import *
from transactflow.multiCurrency import MultiCurrencyAmount
from transactflow.process import *
from transactflow.processes.payslipAnnotationItem import PayslipAnnotationItem

from .helpers import writeTransactionsWithStat

PROCESS_OUTPUT_DIR = "test/processOutput"

@dataclass(frozen=True)
class InvariantContext:
    before: List[Transaction]
    after: List[Transaction]
    processPath: List[Process]

@dataclass(frozen=True)
class InvariantResult:
    satisfied: Optional[bool]
    reason: Optional[str]

def exemptResult(reason: str): return InvariantResult(satisfied=None, reason=reason)

InvariantFn = Callable[[InvariantContext], InvariantResult]

def multiCurrencyAmountDeltaIsNegligible(delta: MultiCurrencyAmount) -> bool:
    return all(amountDeltaIsNegligible(MoneyAmount(c, q)) for c, q in delta.quantities.items())

def makeTotalAccountBalanceUnchangedInvariant(
    payslipAnnotations: List[PayslipAnnotationItem],
) -> InvariantFn:
    def totalAccountBalanceUnchanged(context: InvariantContext) -> InvariantResult:
        totalBefore = totalAccountBalance(context.before)
        totalAfter = totalAccountBalance(context.after)

        delta = totalAfter - totalBefore
        satisfied = multiCurrencyAmountDeltaIsNegligible(delta)
        deltaDescription = ", ".join(
            f"{cur}: {q}" for cur, q in delta.pruningZeroes().quantities.items())

        def resultIfExempt() -> Optional[InvariantResult]:
            process = context.processPath[-1]
            if isinstance(process, transactflow.processes.importer.ImporterProcess):
                return exemptResult("Net total can change normally with loader process")
            if (
                process.label == "applyPayslipAnnotations" and
                delta == transactflow.processes.payslipIncome.expectedTotalBalanceDelta(payslipAnnotations)
            ):
                return exemptResult(f"Delta matches expected amount: {deltaDescription}")
            return None

        if not satisfied and ((exemptRes := resultIfExempt()) is not None):
            return exemptRes

        reason = None if satisfied else f"Unexpected delta: {deltaDescription}"
        return InvariantResult(satisfied, reason)
    return totalAccountBalanceUnchanged

def printInvariantResults(invariantsWithResult: List[Tuple[InvariantFn,  InvariantResult]], process: Process):
    results = [r for _, r in invariantsWithResult]
    allSuccessful = all(r.satisfied == True for r in results)
    allSkipped = all(r.satisfied is None for r in results)
    overallStatusIcon = (
        "❌" if any(r.satisfied == False for r in results)
        else ("✅" if allSuccessful else "⏩")
    )
    print(f"{overallStatusIcon} {process.label}")
    def iconForEach(r: InvariantResult):
        return "⏩" if r.satisfied is None else ("✅" if r.satisfied else "❌")
    def descriptionForEach(invFn: InvariantFn, r: InvariantResult):
        return f"{iconForEach(r)} [{invFn.__name__}]{'' if r.reason is None else ' ' + r.reason}"
    if allSkipped or not allSuccessful:
        for (invFn, result) in invariantsWithResult:
            print(f"    {descriptionForEach(invFn, result)}")

def testGroupedProcess(groupedProcess: GroupedProcess,
                       initialTransactions: List[Transaction],
                       invariants: List[InvariantFn]):
    transactions = initialTransactions
    for path in groupedProcess.iterateDescedants(leafOnly=True, expandAtomic=False):
        process = path[-1]
        before = [ t for t in transactions]
        after = process(transactions)
        context = InvariantContext(before, after, path)
        invFnsWithResult = [(invFn, invFn(context)) for invFn in invariants]
        printInvariantResults(invFnsWithResult, process)
        writeTransactionsWithStat(before, f"{PROCESS_OUTPUT_DIR}/{process.label}_before")
        writeTransactionsWithStat(after, f"{PROCESS_OUTPUT_DIR}/{process.label}_after")
        transactions = after
