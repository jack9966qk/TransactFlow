from transactflow.multiCurrency import MultiCurrencyAmount
from tests.helpers import writeTransactionsWithStat
from transactflow.base import *
from transactflow.process import *
from transactflow.analysis import totalAccountBalance
from typing import Callable
from dataclasses import replace
import transactflow.processes.importer
import transactflow.processes.complex
import transactflow.processes.tax
import transactflow.processes.payslipIncome
import transactflow.processes.runAll

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

def multiCurrencyAmonutDeltaIsNegligible(delta: MultiCurrencyAmount) -> bool:
    return all(amonutDeltaIsNegligible(MoneyAmount(c, q)) for c, q in delta.quantities.items())

def totalAccountBalanceUnchanged(context: InvariantContext) -> InvariantResult:
    totalBefore = totalAccountBalance(context.before)
    totalAfter = totalAccountBalance(context.after)

    delta = totalAfter - totalBefore
    satisfied = multiCurrencyAmonutDeltaIsNegligible(delta)
    deltaDescription = ", ".join(
        f"{cur}: {q}" for cur, q in delta.pruningZeroes().quantities.items())

    def resultIfExempt() -> Optional[InvariantResult]:
        process = context.processPath[-1]
        if isinstance(process, transactflow.processes.importer.ImporterProcess):
            return exemptResult("Net total can change normally with loader process")
        if (
            process == transactflow.processes.payslipIncome.applyPayslipAnnotations and
            delta == transactflow.processes.payslipIncome.expectedTotalBalanceDelta()
        ):
            return exemptResult(f"Delta matches expected amount: {deltaDescription}")
        # if process == transactflow.processes.tax.reprojectUnpaidLocalTaxTo2020:
        #     return exemptResult("Estimated unpaid tax natually affects total")
        # if process == transactflow.processes.tax.addRoughEstimationFor2021TaxPaidIn2022:
        #     return exemptResult("Estimated unpaid tax natually affects total")
        return None

    if not satisfied and ((exemptRes := resultIfExempt()) is not None):
        return exemptRes
    # if not satisfied: breakpoint()

    reason = None if satisfied else f"Unexpected delta: {deltaDescription}"
    return InvariantResult(satisfied, reason)

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

if __name__ == "__main__":
    allCombined = transactflow.processes.runAll.allCombined(includeTaxProcesses=True)
    testGroupedProcess(allCombined, [], [totalAccountBalanceUnchanged])
