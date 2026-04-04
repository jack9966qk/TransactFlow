import unicodedata
import re
from collections import defaultdict
from dataclasses import dataclass
from .base import *
from typing import Dict, Generator, Iterator, List, Literal, Optional, Set, Tuple, Any, Callable, Iterable
from dateutil.parser import parse as parseDate
from abc import ABC, abstractmethod
from tqdm import tqdm

from .multiCurrency import totalAdjustedAmountAsJPY

__all__ = [
    # Type aliases
    "ProcessFn", "MatchFn", "MapFn",
    "MatchFnMaker", "ProcessFnMaker", "ProcessListMaker",

    # Matching
    "Matching", "LabelledFunctionalMatching",
    "funcMatching", "argsDesc", "matching", "funcMatchingWrapper",
    "satisfyAll", "satisfyAny",
    "EVERYTHING", "isSalary", "isDailyShopping", "isMajorShopping",

    # Mapping
    "Mapping", "LabelledFunctionalMapping",
    "funcMapping", "writeCatIf",

    # Process
    "Process", "FunctionProcess", "GroupedProcess", "LazyGroupedProcess",
    "ReplacementProcess",
    "breakpointProcess", "funcProcess", "funcProcessWrapper", "groupedProcessWrapper",
    "filterProc", "mapProc",
    "labelIfMatch", "labelAll",
    "labelSalaryIncome",
    "labelExcludedIncomeIfUncategorizedIncome", "labelGeneralExpenseDestination",
    "relabelShoppingAsDaily", "relabelShoppingAsMajor",
    "takeMatched", "takeFirstMatch",
    "splitTransactionFee",
    "applyRefundOrReimbursement", "labelAndApplyRefundOrReimbursement",
    "monthlySyntheticTransactionsToAdd",
    "addTaxAdjustments", "TaxRedistributionConfig", "collectAndDistributeTax",
    "sortByDate", "sortByDateAndMore", "moveSalaryToFirstOfDay",
]

# ProcessFn :: [Transaction] -> [Transaction]
ProcessFn = Callable[[List[Transaction]], List[Transaction]]
# MatchingFn :: Transaction -> bool
MatchFn = Callable[[Transaction], bool]
# MapFn :: Transaction -> Transaction
MapFn = Callable[[Transaction], Transaction]

class Matching(ABC):
    label: str
    @abstractmethod
    def __call__(self, transaction: Transaction) -> bool:
        pass

class LabelledFunctionalMatching(Matching):
    def __init__(self, matching: MatchFn, label: str):
        self.matching: MatchFn = matching
        self.label: str = label
    def __repr__(self):
        return f"Matching: {self.label}"
    def __call__(self, transaction: Transaction) -> bool:
        return self.matching(transaction)

def funcMatching(customLabel: Optional[str] = None) -> Callable[[MatchFn], LabelledFunctionalMatching]:
    def labelMatchingWithFuncName(matchingFn: MatchFn) -> LabelledFunctionalMatching:
        label = customLabel if customLabel is not None else matchingFn.__name__
        return LabelledFunctionalMatching(matchingFn, label)
    return labelMatchingWithFuncName

def argsDesc(args: Iterable[Tuple[str, Any]]) -> str:
    return ", ".join([f"{arg}={val}" for arg, val in args if val is not None])

def matching(
    account: Optional[Account] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    day: Optional[int] = None,
    exactCategory: Optional[Category] = None,
    exactDesc: Optional[str] = None,
    descSubstr: Optional[str] = None,
    anyDescSubStr: Optional[List[str]] = None,
    anyDescRegex: Optional[List[str | re.Pattern[str]]] = None,
    normalizeDesc: bool = False,
    descRegexIgnoreCase: bool = False,
    amountPosNegIs: Optional[Literal["pos"] | Literal["neg"]] =  None,
    quantity: Optional[float] = None,
    adjustedQuantity: Optional[float] = None,
    dateFrom: Optional[Date] = None,
    dateUntil: Optional[Date] = None,
    date: Optional[str] = None,
    rawRecord: Optional[str] = None,
    breakpointOnTransaction: Optional[Callable[[Transaction], bool]] = None
) -> LabelledFunctionalMatching:
    label = argsDesc(locals().items())
    def matchingFn(t: Transaction) -> bool:
        if (fn := breakpointOnTransaction) is not None:
            if fn(t): breakpoint()
        # Below may be helpful for debugging.
        # if "申告所得税及復興特別所得税" in t.description and t.account == AMEX_JP and "申告所得税及復興特別所得税" == descSubstr:
        #     breakpoint()
        #     pass
        # For regex debugging:
        # re.search(r"...", unicodedata.normalize('NFKC', "..."), re.IGNORECASE)
        def description():
            return unicodedata.normalize('NFKC', t.description) if normalizeDesc else t.description
        if account is not None:
            if t.account != account: return False
        if dateFrom is not None:
            if t.date < dateFrom: return False
        if dateUntil is not None:
            if t.date > dateUntil: return False
        if date is not None:
            dateObj = parseDate(date).date()
            if t.date.year != dateObj.year: return False
            if t.date.month != dateObj.month: return False
            if t.date.day != dateObj.day: return False
        if year is not None:
            if t.date.year != year: return False
        if month is not None:
            if t.date.month != month: return False
        if day is not None:
            if t.date.day != day: return False
        if exactCategory is not None:
            if t.category != exactCategory: return False
        if exactDesc is not None:
            if exactDesc != description(): return False
        if descSubstr is not None:
            if not descSubstr in description(): return False
        if anyDescSubStr is not None:
            if all((not s in description()) for s in anyDescSubStr):
                return False
        if anyDescRegex is not None:
            reArgs = [re.IGNORECASE] if descRegexIgnoreCase else []
            d = description()
            def reMatch(r): return re.search(r, d, *reArgs)
            if all((not reMatch(r)) for r in anyDescRegex):
                return False
        if quantity is not None:
            if t.rawAmount.quantity != quantity: return False
        if adjustedQuantity is not None:
            if t.adjustedAmount.quantity != adjustedQuantity: return False
        if amountPosNegIs is not None:
            posNeg = "pos" if t.rawAmount.quantity >= 0 else "neg"
            if amountPosNegIs not in ["pos", "neg"]: assert(False)
            if amountPosNegIs != posNeg: return False
        if rawRecord is not None:
            if t.rawRecord.strip() != rawRecord.strip(): return False
        return True
    return LabelledFunctionalMatching(matchingFn, label)

MatchFnMaker = Callable[[], MatchFn]
def funcMatchingWrapper(customLabel: Optional[str] = None) -> Callable[[MatchFnMaker], LabelledFunctionalMatching]:
    def labelMatchingWithFuncName(matchingFnMaker: MatchFnMaker) -> LabelledFunctionalMatching:
        matchingFn = matchingFnMaker()
        label = customLabel if customLabel is not None else matchingFnMaker.__name__
        return LabelledFunctionalMatching(matchingFn, label)
    return labelMatchingWithFuncName

class Process(ABC):
    label: str
    def __init__(self, label): self.label = label
    def __repr__(self): return f"<Process: {self.label}>"
    @abstractmethod
    def __call__(self, transactions: List[Transaction]) -> List[Transaction]:
        pass

class FunctionProcess(Process):
    def __init__(self, process: ProcessFn, label: str):
        super().__init__(label)
        self.process: ProcessFn = process
    def __repr__(self):
        return f"FnProc: {self.label}"
    def __call__(self, transactions: List[Transaction]) -> List[Transaction]:
        return self.process(transactions)

class GroupedProcess(Process):
    processes: List[Process]
    atomic: bool
    def __init__(self, label: Optional[str] = None, atomic: bool = False, processes: Optional[List[Process]] = None):
        label = "Anonymous grouped process" if label is None else label
        super().__init__(label)
        self.processes = [] if processes is None else processes
        self.atomic = atomic
    def __call__(self, transactions: List[Transaction], progress = False) -> List[Transaction]:
        result = transactions
        flattenPaths = list(self.iterateDescedants(leafOnly=True, expandAtomic=self.atomic))
        shouldDisplayProgress = (not self.atomic and progress)
        if shouldDisplayProgress: flattenPaths = tqdm(flattenPaths, desc=self.label)
        for path in flattenPaths:
            process = path[-1]
            if shouldDisplayProgress:
                tqdm.write(f"Running {process.label}")
            result = process(result)
        return result
    def iterateDescedants(
        self, leafOnly: bool, expandAtomic: bool
    ) -> Generator[List[Process], None, None]:
        visited: set[int] = set()
        def iterateDescedantsRec(process: Process, pathUntilProc: List[Process]):
            def processToExpand():
                if not isinstance(process, GroupedProcess): return None
                if process.atomic and not expandAtomic: return None
                if leafOnly: return process
                return process
            if (toExpand := processToExpand()) is not None:
                processId = id(toExpand)
                if processId in visited:
                    ancestors = " -> ".join(p.label for p in pathUntilProc)
                    raise ValueError(
                        f"Cycle detected in GroupedProcess traversal: "
                        f"'{toExpand.label}' already visited. "
                        f"Path: {ancestors} -> {toExpand.label}"
                    )
                visited.add(processId)
                for p in toExpand.processes:
                    yield from iterateDescedantsRec(p, pathUntilProc + [process])
                visited.discard(processId)
            else:
                yield pathUntilProc + [process]
        yield from iterateDescedantsRec(self, [])
    def printTree(self):
        for path in self.iterateDescedants(leafOnly=False, expandAtomic=False):
            print("    " * (len(path) - 1) + path[-1].label)

class LazyGroupedProcess(GroupedProcess):
    """A GroupedProcess that defers process list construction to first use.

    Needed because module-level process variables are evaluated at import time,
    but UserConfig is set later via setUserConfig().

    Uses a property for `processes` so that resolution is triggered even when a
    parent GroupedProcess accesses `.processes` directly during iteration.
    """
    _buildProcesses: Callable[[], List["Process"]]
    _resolved: bool
    _processes_list: List["Process"]

    def __init__(self, label: str, buildProcesses: Callable[[], List["Process"]], atomic: bool = False):
        super().__init__(label=label, atomic=atomic, processes=[])
        self._buildProcesses = buildProcesses
        self._resolved = False

    @property  # type: ignore[override]
    def processes(self) -> List["Process"]:
        if not self._resolved:
            self._processes_list = self._buildProcesses()
            self._resolved = True
        return self._processes_list

    @processes.setter
    def processes(self, value: List["Process"]):
        self._processes_list = value


def breakpointProcess(*args) -> Process:
    @funcProcess(f"Breakpoint")
    def func(transactions: List[Transaction]) -> List[Transaction]:
        breakpoint()
        print(args)
        return transactions
    return func

def funcProcess(customLabel: Optional[str] = None) -> Callable[[ProcessFn], FunctionProcess]:
    def labelProcessWithFuncName(processFn: ProcessFn) -> FunctionProcess:
        label = customLabel if customLabel is not None else processFn.__name__
        return FunctionProcess(processFn, label)
    return labelProcessWithFuncName

ProcessFnMaker = Callable[[], ProcessFn]
def funcProcessWrapper(
    customLabel: Optional[str] = None
) -> Callable[[ProcessFnMaker], FunctionProcess]:
    def labelProcessWithFuncName(processFnMaker: ProcessFnMaker) -> FunctionProcess:
        processFn = processFnMaker()
        label = customLabel if customLabel is not None else processFnMaker.__name__
        return FunctionProcess(processFn, label)
    return labelProcessWithFuncName

ProcessListMaker = Callable[[], List[Process]]
def groupedProcessWrapper(
    customLabel: Optional[str] = None, atomic: bool = True
) -> Callable[[ProcessListMaker], GroupedProcess]:
    def labelProcessWithFuncName(processListMaker: ProcessListMaker) -> GroupedProcess:
        processes = processListMaker()
        label = customLabel if customLabel is not None else processListMaker.__name__
        return GroupedProcess(label=label, atomic=atomic, processes=processes)
    return labelProcessWithFuncName

def filterProc(matching: Matching) -> Process:
    @funcProcess(f"Filter with {matching.label}")
    def func(transactions: List[Transaction]) -> List[Transaction]:
        return [t for t in transactions if matching(t)]
    return func

class Mapping(ABC):
    label: str
    @abstractmethod
    def __call__(self, transaction: Transaction) -> Transaction:
        pass

class LabelledFunctionalMapping(Mapping):
    def __init__(self, mapping: MapFn, label: str):
        self.mapping: MapFn = mapping
        self.label: str = label
    def __repr__(self):
        return f"FnMap: {self.label}"
    def __call__(self, transaction: Transaction) -> Transaction:
        return self.mapping(transaction)

def funcMapping(customLabel: Optional[str] = None) -> Callable[[MapFn], LabelledFunctionalMapping]:
    def labelMappingWithFuncName(mapFn: MapFn) -> LabelledFunctionalMapping:
        label = customLabel if customLabel is not None else mapFn.__name__
        return LabelledFunctionalMapping(mapFn, label)
    return labelMappingWithFuncName

def mapProc(mapping: Mapping) -> Process:
    @funcProcess(f"Map with {mapping.label}")
    def func(transactions: List[Transaction]) -> List[Transaction]:
        return [mapping(t) for t in transactions]
    return func

def writeCatIf(matching: Matching, category: Category) -> Mapping:
    @funcMapping(f"write cat if {matching.label}")
    def func(t: Transaction) -> Transaction:
        return t.replacingCategory(category) if matching(t) else t
    return func

def satisfyAll(matchings: List[Matching]) -> Matching:
    @funcMatching(f"Satisfy all of f{[m.label for m in matchings]}")
    def func(t: Transaction):
        for matching in matchings:
            if not matching(t): return False
        return True
    return func

def satisfyAny(matchings: List[Matching]) -> Matching:
    @funcMatching(f"Satisfy any of f{[m.label for m in matchings]}")
    def func(t: Transaction):
        for matching in matchings:
            if matching(t): return True
        return False
    return func

def labelIfMatch(matching: Matching,
                 account: Optional[Account] = None,
                 category: Optional[Category] = None,
                 relatedTo: Optional[Account] = None,
                 description: Optional[str] = None,
                 comment: Optional[str] = None,
                 expected: Optional[int] = None) -> Process:
    label = f"labelIfMatch({argsDesc(locals().items())})"
    @funcProcess()
    def checkMatchingExpectedNum(transactions: List[Transaction]) -> List[Transaction]:
        numMatching = sum(1 for t in transactions if matching(t))
        passing = numMatching == expected if expected is not None else numMatching > 0
        if not passing: breakpoint()
        return transactions
    @funcMapping()
    def mapOne(t: Transaction) -> Transaction:
        if not matching(t): return t
        result = t
        if account is not None: result = result.replacingAccount(account)
        if category is not None: result = result.replacingCategory(category)
        if relatedTo is not None: result = result.replacingRelatedTo(relatedTo)
        if description is not None: result = result.replacingDescription(description)
        if comment is not None: result = result.replacingComment(comment)
        return result
    return GroupedProcess(
        label=label,
        atomic=True,
        processes=[checkMatchingExpectedNum, mapProc(mapOne)])

EVERYTHING = funcMatching("Everything")(lambda _: True)

def labelAll(account=None, category=None, relatedTo=None):
    return labelIfMatch(EVERYTHING, account=account, category=category, relatedTo=relatedTo)

@funcMatching()
def isSalary(t: Transaction) -> bool:
    destMatches = t.relatedTo == EMPLOYER
    return t.rawAmount.quantity > 0 and destMatches

labelSalaryIncome = labelIfMatch(isSalary, category=SALARY)

@funcProcessWrapper()
def labelExcludedIncomeIfUncategorizedIncome(): return labelIfMatch(
    matching(amountPosNegIs="pos", exactCategory=INCOME),
    category=EXCLUDED_INCOME, relatedTo=OTHER_INCOME_SOURCE)

@funcProcessWrapper()
def labelGeneralExpenseDestination(): return labelIfMatch(
    matching(amountPosNegIs="neg", exactCategory=EXPENSE),
    relatedTo=GENERAL_EXPENSE_DESTINATION)

@funcMatching()
def isDailyShopping(t: Transaction) -> bool:
    return t.rawAmount.currency == JPY and t.rawAmount.quantity > -10000 and t.category == SHOPPING
@funcProcessWrapper()
def relabelShoppingAsDaily(): return labelIfMatch(isDailyShopping, category=DAILY_SHOPPING)

@funcMatching()
def isMajorShopping(t: Transaction) -> bool:
    return t.rawAmount.currency == JPY and t.rawAmount.quantity <= -10000 and t.category == SHOPPING
@funcProcessWrapper()
def relabelShoppingAsMajor(): return labelIfMatch(isMajorShopping, category=MAJOR_SHOPPING)

def takeMatched(
    transactions: List[Transaction], matching: Matching, limit: Optional[int] = None
) -> Tuple[List[Transaction], List[Transaction]]:
    matched: List[Transaction] = []
    remaining: List[Transaction] = []
    for t in transactions:
        acceptMatching = False
        if limit is None: acceptMatching = True
        elif len(matched) < limit: acceptMatching = True
        if acceptMatching and matching(t):
            matched.append(t)
        else: remaining.append(t)
    return matched, remaining

def takeFirstMatch(trans: List[Transaction], matching: Matching):
    matched, remaining = takeMatched(trans, matching, limit=1)
    match matched:
        case []: return None, remaining
        case [t]: return t, remaining
        case _: assert(False)

class ReplacementProcess(Process):
    def __init__(self, label: str,
                 replaceFirstMatches: List[Matching],
                 replaceFn: Callable[[List[Transaction]], List[Transaction]]):
        super().__init__(label)
        self.replaceFirstMatches = replaceFirstMatches
        self.replaceFn = replaceFn
    def __repr__(self):
        return f"Replacement: {self.label}"
    def __call__(self, transactions):
        processedTrans = transactions
        matchedTrans = []
        for matching in self.replaceFirstMatches:
            matched, processedTrans = takeFirstMatch(processedTrans, matching)
            assert(matched is not None)
            matchedTrans.append(matched)
        processedTrans.extend(self.replaceFn(matchedTrans))
        processedTrans.sort(key=lambda t: t.date)
        return processedTrans

def splitTransactionFee(match: Matching, feeName, feeAbsAmount: MoneyAmount) -> Process:
    def replaceFn(matches: List[Transaction]) -> List[Transaction]:
        assert(len(matches) == 1)
        paymentTransaction = matches[0]
        assert(paymentTransaction.rawAmount.currency == feeAbsAmount.currency)
        return [
            paymentTransaction.addingAdjustment(feeAbsAmount.quantity),
            syntheticTransaction(
                date=paymentTransaction.date,
                description=f"Synthetic transaction: {feeName}",
                amount=-feeAbsAmount,
                category=EXPENSE,
                account=paymentTransaction.account)
        ]
    return ReplacementProcess(
        label="overwritten by parent", replaceFirstMatches=[match], replaceFn=replaceFn)

def applyRefundOrReimbursement(expenseMatches: List[Matching],
                               reimbursementMatch: Matching,
                               label=None) -> ReplacementProcess:
    # ReplacementProcess takes a list and does not tell between its items. In this case, the last
    # item is for the reimbursement, and the items before that are for the expenses.
    mergedMatchings = expenseMatches + [reimbursementMatch]
    def splitMatches(matches: List[Transaction]): return matches[:-1], matches[-1]

    def replaceFn(matches: List[Transaction]) -> List[Transaction]:
        expenses, reimbursement = splitMatches(matches)
        assert(reimbursement.category == REFUND_REIMBURSEMENT)

        processedExpenses = []
        for exp in expenses:
            # Take into account the case where reimbursement does not have enough balance.
            assert(reimbursement.adjustedAmount.currency == exp.adjustedAmount.currency)
            amountToReimburse = min(reimbursement.adjustedAmount.quantity,
                                    -exp.adjustedAmount.quantity)
            if amountToReimburse == 0:
                # Usually would reach a point where the function attempts to apply a reimbusement
                # that already has no amount left.
                breakpoint()
                processedExpenses.append(exp)
            else:
                processedExpenses.append(exp.addingAdjustment(amountToReimburse))
                reimbursement = reimbursement.addingAdjustment(-amountToReimburse)
        return processedExpenses + [reimbursement]
    return ReplacementProcess(
        label=(label if label is not None
               else f"applyRefundOrReimbursement with matching: {reimbursementMatch.label}"),
        replaceFirstMatches=mergedMatchings, replaceFn=replaceFn)

def labelAndApplyRefundOrReimbursement(expenseMatches: List[Matching],
                                       reimbursementMatch: Matching,
                                       label=None) -> Process:
    return GroupedProcess(atomic=True, processes=[
        labelIfMatch(reimbursementMatch, category=REFUND_REIMBURSEMENT),
        applyRefundOrReimbursement(expenseMatches, reimbursementMatch, label=label)
    ])

def monthlySyntheticTransactionsToAdd(
    splitRatio: Dict[int, float],
    syntheticTranssactionForMonth: Callable[[int, MoneyAmount], Transaction],
    totalAmount: MoneyAmount
) -> List[Transaction]:
    """
    Split total amount to each month of the year, and generate synthetic transactions for each
    month if any amount. Amount can be positive or negative, splitRatio maps from month to a float
    of any positive number, representing ratio for each month of the year.
    `pseudoTransactionForMonth` is a function that takes month and amount as argument, and returns
    the synthetic transaction to be added.
    """
    if totalAmount.quantity == 0: return []
    ratioSum = sum(splitRatio.values())
    normalizedRatio = { k: v / ratioSum for k, v in splitRatio.items() }
    # Sanity check ratios are correctly calculated.
    assert(0.999 < sum(normalizedRatio.values()) < 1.001)
    def generateTransactions():
        for month, ratio in normalizedRatio.items():
            synthetic = syntheticTranssactionForMonth(month, totalAmount * ratio)
            assert(synthetic.adjustedAmount == totalAmount * ratio)
            yield synthetic
    return list(generateTransactions())

def addTaxAdjustments(transactions: List[Transaction],
                      totalAbsAmount: MoneyAmount,
                      toYear: int,
                      weightUsingExactIncomeCat: Category,
                      taxDescription: str,
                      taxCategory: Category,
                      taxAccount: Account) -> List[Transaction]:
    """
    Split total tax amount into each month of the year by the ratio of taxable income total
    in each month. Then add these numbers as artificial expense items to each month. The tax
    expenses included in this provided total amount should be cleared (e.g adjusted to 0) before
    calling this function.
    """
    assert(taxCategory.isUnder(TAX))
    assert(totalAbsAmount.quantity >= 0)
    if totalAbsAmount.quantity == 0: return transactions
    weightingTransactions = [t for t in transactions
                             if t.date.year == toYear and
                             t.category == weightUsingExactIncomeCat]
    totalWeightingAmount = totalAdjustedAmountAsJPY(weightingTransactions)
    def transactionsToAdd(isForecast: bool) -> List[Transaction]:
        transactionsByMonth: Dict[int, List[Transaction]] = defaultdict(list)
        for t in weightingTransactions:
            if t.isForecast != isForecast: continue
            transactionsByMonth[t.date.month].append(t)
        if len(transactionsByMonth) == 0: return []
        weightingTotalsByMonth = {
            month: totalAdjustedAmountAsJPY(transactions)
            for month, transactions in transactionsByMonth.items()
        }
        totalAbsAmountToAdd = (
            totalAbsAmount * sum(weightingTotalsByMonth.values()) / totalWeightingAmount
        )
        def pseudoTransactionForMonth(month: int, amount: MoneyAmount):
            # TODO: Avoid having placeholder day.
            return syntheticTransaction(
                date=Date(year=toYear, month=month, day=26),
                description=f"Synthetic tax item for {taxDescription} at {toYear}/{month}",
                amount=amount,
                category=taxCategory,
                account=taxAccount,
                isForecast=isForecast)
        return monthlySyntheticTransactionsToAdd(
            splitRatio=weightingTotalsByMonth,
            syntheticTranssactionForMonth=pseudoTransactionForMonth,
            totalAmount=-totalAbsAmountToAdd)
    allTransactionsToAdd = (
        transactionsToAdd(isForecast=True) + transactionsToAdd(isForecast=False)
    )
    totalNegAmountAdded = sumSingleCurrencyAmounts(t.adjustedAmount for t in allTransactionsToAdd)
    assert(amountDeltaIsNegligible(totalAbsAmount + totalNegAmountAdded))
    return sortByDateAndMore(transactions + allTransactionsToAdd)

@dataclass
class TaxRedistributionConfig:
    taxDescription: str
    taxCategory: Category
    # 0 if not tax relevant trans
    getChargedTaxAbsAmount: Callable[[Transaction], float]
    verifyTotalTaxAmount: Optional[MoneyAmount] = None
    runProcessWithTotalTaxAmount: Optional[Callable[[MoneyAmount], Process]] = None


def collectAndDistributeTax(
    toYear: int,
    label: str,
    configForWeightingCategory: Dict[Category, TaxRedistributionConfig]
) -> Process:
    """
    Sometimes tax for one year is charged in a single month, or even in a different year.
    Collect all tax-relevant transactions (that is, all transactions where getChargedTaxAbsAmount
    returns value > 0), remove these amounts from the transactions, and distribute the total
    amount to the specified year.
    """
    @funcProcess(customLabel=label)
    def func(transactions: List[Transaction]) -> List[Transaction]:
        def separateTaxFromTransaction(
            transaction: Transaction,
        ) -> Tuple[Transaction, Dict[Category, MoneyAmount]]:
            def absTaxQuantityFor(config: TaxRedistributionConfig) -> float:
                amount = config.getChargedTaxAbsAmount(transaction)
                if amount > 0:
                    assert(transaction.adjustedAmount.quantity < 0)
                    assert(amount <= abs(transaction.adjustedAmount.quantity))
                return amount
            taxQuantityForWeightingCategory = {
                cat: absTaxQuantityFor(config)
                for cat, config in configForWeightingCategory.items()
            }
            def maybeAdjustedTransaction():
                adjusted = transaction
                for quantity in taxQuantityForWeightingCategory.values():
                    assert(quantity >= 0)
                    if quantity == 0: continue
                    adjusted = adjusted.addingAdjustment(quantity)
                return adjusted
            taxAmountForCategory = {
                cat: MoneyAmount(transaction.rawAmount.currency, quantity)
                for cat, quantity in taxQuantityForWeightingCategory.items()
                if quantity > 0
            }
            return maybeAdjustedTransaction(), taxAmountForCategory
        transactionsWithTaxAmounts = [separateTaxFromTransaction(t) for t in transactions]
        updatedTransactions = [t for t, _ in transactionsWithTaxAmounts]
        for category, config in configForWeightingCategory.items():
            totalAmountForAccount: Dict[Account, MoneyAmount] = defaultdict(lambda: EMPTY_AMOUNT)
            for t, mapping in transactionsWithTaxAmounts:
                amountForCat = mapping.get(category, None)
                if amountForCat is None: continue
                totalAmountForAccount[t.account] += amountForCat
            # if JCB_CREDIT_CARD in totalAmountForAccount:
            #     breakpoint()
            totalChargedAmount = sumSingleCurrencyAmounts(totalAmountForAccount.values())
            if config.verifyTotalTaxAmount is not None:
                assert(totalChargedAmount == config.verifyTotalTaxAmount)
            for account, totalForAccount in totalAmountForAccount.items():
                if totalForAccount.quantity == 0: continue
                lenBefore = len(updatedTransactions)
                updatedTransactions = addTaxAdjustments(
                    transactions=updatedTransactions,
                    totalAbsAmount=totalForAccount,
                    toYear=toYear,
                    weightUsingExactIncomeCat=category,
                    taxDescription=config.taxDescription,
                    taxCategory=config.taxCategory,
                    taxAccount=account)
                assert(len(updatedTransactions) > lenBefore)
            if config.runProcessWithTotalTaxAmount:
                updatedTransactions = config.runProcessWithTotalTaxAmount(totalChargedAmount)(updatedTransactions)
        return updatedTransactions
    return func

@funcProcess()
def sortByDate(ts: List[Transaction]):
    return sorted(ts, key=lambda t: t.date)

@funcProcess()
def sortByDateAndMore(ts: List[Transaction]):
    def key(t: Transaction):
        sourceLocationKey = ("", 0)
        if (sourceLocation := t.sourceLocation) is not None:
            filePath, lineNum = sourceLocation
            sourceLocationKey = (filePath, abs(lineNum))
        return (
            t.date,
            t.account,
            sourceLocationKey,
        )
    return sorted(ts, key=key)

from itertools import groupby
@funcProcess()
def moveSalaryToFirstOfDay(trans: List[Transaction]) -> List[Transaction]:
    """
    When there are multiple transactions on one day, move salary income to the top.
    Because they are on the same day, it should be safe against sorting by date later.
    """
    trans = sortedByDate(trans)
    results = []
    for _, sameDateGroup in groupby(trans, key=lambda t:t.date):
        sameDateGroup = list(sameDateGroup)
        isSalaryIncome = lambda t: t.category == SALARY
        reordered = ([t for t in sameDateGroup if isSalaryIncome(t)] +
                     [t for t in sameDateGroup if not isSalaryIncome(t)])
        results.extend(reordered)
    return results
