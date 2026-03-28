from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from rates import RetrivedRates, getOrRetrieveLatestRates
from base import *
from multiCurrency import MultiCurrencyAmount, embeddedOrLatestRatesFor, sumCurrencyAmounts, amountInJPY, totalAdjustedAmount, totalAdjustedAmountAsJPY, totalRawAmount, totalRawAmountAsJPY
from typing import Callable, DefaultDict, FrozenSet, Generator, List, Dict, Optional, Set, Tuple, TypeVar, Union, cast
from collections import OrderedDict
from processes.sharedMatchings import *
import itertools

# @dataclass
# class StringTable:
#     class Cell:
#         text: str
#         isHeader: bool = False
#         htmlStyle: Optional[str] = None
#     cells: List[List["StringTable.Cell"]]

#     @property
#     def asHTMLTable(self) -> str:
#         def renderCell(cell: "StringTable.Cell"):
#             tag = "th" if cell.isHeader else "td"
#             attr = f' style="{style}"' if (style := cell.htmlStyle) is not None else ""
#             yield f"<{tag}{attr}>{cell.text}</{tag}>"
#         def renderRow(row: List["StringTable.Cell"]):
#             yield f"<tr>"
#             for cell in row: yield from renderCell(cell)
#             yield f"</tr>"
#         def renderTable():
#             yield "<table>"
#             for row in self.cells: yield from renderRow(row)
#             yield "</table>"
#         return "\n".join(list(renderTable()))

def transListToHtmlTable(trans: Iterable[Transaction], colorOn=False):
    def toHtmlRow(t: Transaction):
        if any(
            t.category.isUnder(cat)
            for cat in [NOT_REALLY_INCOME, INTERNAL_TRANSFER]
        ):
            colorCode = IRRELEVANT_COLOR_CODE
        else:
            # TODO: Better support for other currencies.
            colorCode = colorCodeForJPYAmount(
                amountInJPY(t.adjustedAmount, embeddedOrLatestRatesFor(t))
            )
        style = f"background-color: {colorCode}" if colorOn else ""
        return f"""
            <tr>
                <td>{t.category.label}</td>
                <td>{t.date}</td>
                <td>{t.account}</td>
                <td style="{style}">{t.adjustedAmount.quantity:.2f}</td>
                <td>{t.rawAmount.quantity:.2f}</td>
                <td>{t.relatedTo if t.relatedTo != None else ""}</td>
                <td><pre>{t.description}</pre></td>
            </tr>
        """

    rows = "\n".join(toHtmlRow(t) for t in trans)
    return f"""
        <table>
            <tr>
                <th>Category</th>
                <th>Date</th>
                <th>Account</th>
                <th>Amount</th>
                <th>Raw amount</th>
                <th>Related to</th>
                <th>Description</th>
            </tr>
        {rows}
        </table>
    """

class PseudoCategory(Category): pass

ORDERED_PSEUDO_CATEGORIES = [
    ANY_CATEGORY := PseudoCategory("Any"),
    OTHER := PseudoCategory("Other"),
    REMAINING := PseudoCategory("Remaining"),
    SALARY_AFTER_DEDUCTION := PseudoCategory("Salary (after deduction)", parent=EARNED_INCOME),
    BONUS_AFTER_DEDUCTION := PseudoCategory("Bonus (after deduction)", parent=EARNED_INCOME),
    EQUITY_AFTER_DEDUCTION := PseudoCategory("Equity (after deduction)", parent=EARNED_INCOME),
]

CategoryTransformer = Callable[[Category], Category]

@dataclass(frozen=True)
class AnnotatedCategory:
    category: Category
    isForecast: bool
    @property
    def label(self):
        suffix = " (forecasted)" if self.isForecast else ""
        return f"{self.category.label}{suffix}"
    def transformCategory(self, transformer: CategoryTransformer):
        return AnnotatedCategory(category=transformer(self.category), isForecast=self.isForecast)

def reduceToAncestorOfDepth(lvl: int) -> CategoryTransformer:
    assert(lvl >= 0)
    @memo
    def categorizeByAncestor(c: Category) -> Category:
        return c.ancestorBy(c.depth - lvl)
    return categorizeByAncestor

# Group label (e.g. "2019-03-25~", "2020"...)
GroupLabel = str

class CurrencyConversionMode(Enum):
    """
    How amounts in multiple currencies are unified.
    """
    USE_RATES_NEAREST_TRANSACTION = "Use rates nearest to transaction"
    USE_LATEST_RATES = "Use latest rates"

@dataclass
class TransactionSetStats:
    transactions: List[Transaction]
    currencyConversionMode: CurrencyConversionMode = CurrencyConversionMode.USE_RATES_NEAREST_TRANSACTION

    def totalAdjustedAmountAsJPYFor(self, transactions: Iterable[Transaction]) -> float:
        match self.currencyConversionMode:
            case CurrencyConversionMode.USE_RATES_NEAREST_TRANSACTION:
                return totalAdjustedAmountAsJPY(transactions)
            case CurrencyConversionMode.USE_LATEST_RATES:
                return sumCurrencyAmounts(
                    t.adjustedAmount for t in transactions
                ).aggregatedUsingLatestRatesAs(JPY)

    def totalRawAmountAsJPYFor(self, transactions: Iterable[Transaction]) -> float:
        match self.currencyConversionMode:
            case CurrencyConversionMode.USE_RATES_NEAREST_TRANSACTION:
                return totalRawAmountAsJPY(transactions)
            case CurrencyConversionMode.USE_LATEST_RATES:
                return sumCurrencyAmounts(
                    t.rawAmount for t in transactions
                ).aggregatedUsingLatestRatesAs(JPY)

    @property
    def nonForecastSubset(self) -> "TransactionSetStats":
        return TransactionSetStats(
            transactions=[t for t in self.transactions if not t.isForecast],
            currencyConversionMode=self.currencyConversionMode)

    @property
    def forecastSubset(self) -> "TransactionSetStats":
        return TransactionSetStats(
            transactions=[t for t in self.transactions if t.isForecast],
            currencyConversionMode=self.currencyConversionMode)

    @property
    def nonForecastRemainingAmountAsJPY(self) -> float:
        subset = self.nonForecastSubset
        return max(0, subset.totalEarnedIncomeAsJPY - abs(subset.totalExpenseAsJPY))

    @property
    def forecastRemainingAmountAsJPY(self) -> float:
        subset = self.forecastSubset
        return max(0, subset.totalEarnedIncomeAsJPY - abs(subset.totalExpenseAsJPY))

    @property
    def totalEarnedIncomeAsJPY(self) -> float:
        return self.totalAdjustedAmountAsJPYFor(earnedIncomesOf(self.transactions))
    @property
    def totalExpenseAsJPY(self) -> float:
        return self.totalAdjustedAmountAsJPYFor(expensesOf(self.transactions))

    @property
    def totalAdjustedAmountAsJPY(self) -> float:
        return self.totalAdjustedAmountAsJPYFor(self.transactions)

    @property
    def totalEarnedIncome(self) -> MultiCurrencyAmount:
        return sumCurrencyAmounts(t.adjustedAmount for t in earnedIncomesOf(self.transactions))
    @property
    def totalExpense(self) -> MultiCurrencyAmount:
        return sumCurrencyAmounts(abs(t.adjustedAmount) for t in expensesOf(self.transactions))

    def categorizedTotalsAsJPY(self, absVals: bool = False) -> Dict[AnnotatedCategory, float]:
        transSets: Dict[AnnotatedCategory, Set[Transaction]] = defaultdict(set)
        for t in self.transactions:
            key = AnnotatedCategory(category=t.category, isForecast=t.isForecast)
            transSets[key].add(t)
        def maybeAbs(f: float): return f if not absVals else abs(f)
        return {
            k: maybeAbs(self.totalAdjustedAmountAsJPYFor(ts))
            for k, ts in transSets.items()
        }

    @dataclass
    class ExpenseSummary:
        amountsByCategory: Dict[AnnotatedCategory, float]
        totalAmount: float

    def expenseSummary(self, includeRemaining: bool) -> ExpenseSummary:
        expenses = expensesOf(self.transactions)
        totalByCats = TransactionSetStats(expenses).categorizedTotalsAsJPY(absVals=True)
        if includeRemaining:
            nonForecastRemaining = AnnotatedCategory(category=REMAINING, isForecast=False)
            forecastRemaining = AnnotatedCategory(category=REMAINING, isForecast=True)
            totalByCats[nonForecastRemaining] = self.nonForecastRemainingAmountAsJPY
            totalByCats[forecastRemaining] = self.forecastRemainingAmountAsJPY
        totalAmount = sum(totalByCats.values())
        return TransactionSetStats.ExpenseSummary(totalByCats, totalAmount)

def reorderCategories(categories: List[Category],
                      leading: List[Category] = [],
                      trailing: List[Category] = [],
                      exclude: List[Category] = []) -> List[Category]:
    result = categories
    for cat in leading[::-1]:
        result = [cat] + [c for c in result if c != cat]
    for cat in trailing:
        result = [c for c in result if c != cat] + [cat]
    result = [c for c in result if c not in exclude]
    return result

def transactionsOverview(label: str, transactions: List[Transaction]) -> str:
    lines = []
    for currencyConversionMode in CurrencyConversionMode:
        lines.append(f"Conversion mode: {currencyConversionMode.value}")
        stats = TransactionSetStats(transactions, currencyConversionMode)
        earnedIncomesTotal = stats.totalEarnedIncomeAsJPY
        expensesTotal = abs(stats.totalExpenseAsJPY)
        totalRent = TransactionSetStats(
            [t for t in transactions if t.category.isUnder(RENT)]
        ).totalAdjustedAmountAsJPY
        earnedIncomeMinusRent = earnedIncomesTotal - totalRent
        incomeExpenseDesc = f"{label} (as JPY): {int(earnedIncomesTotal):>7d} - {int(expensesTotal):<7d} = {int(earnedIncomesTotal - expensesTotal):7d}"
        if earnedIncomeMinusRent < 0:
            return f"{incomeExpenseDesc}\n"
        percentage = (earnedIncomesTotal - expensesTotal) / earnedIncomesTotal * 100
        percentageWithoutRent = (earnedIncomesTotal - expensesTotal) / earnedIncomeMinusRent * 100
        lines += [
            incomeExpenseDesc,
            f"             Remaining is (as JPY) {int(percentage):2d}% of total income, {int(percentageWithoutRent):2d}% of (income - rent)"
        ]
    return "\n".join(lines)

"""
Calculates the unified amount of account balance as of now.

Ideally, the results should match the sum of all "current balance" amounts among all banks or
brokers.
"""
totalAccountBalance = totalRawAmount

def accountBalanceByAccount(transactions: List[Transaction]) -> Dict[Account, MultiCurrencyAmount]:
    transactionsByAccount: Dict[Account, List[Transaction]] = defaultdict(list)
    for t in transactions: transactionsByAccount[t.account].append(t)
    return { a: totalAccountBalance(ts) for a, ts in transactionsByAccount.items() }

def netWorth(transactions: List[Transaction]) -> MultiCurrencyAmount:
    """
    Calculates the net worth of all available assets.

    This includes some unrealized but determined deductions such as unpaid tax, but does not
    include potential deductions from currency exchange or capital gain that is not realized.
    """
    return totalAdjustedAmount(
        t for t in transactions
        if not t.isForecast and
        not t.category.isUnderAny([
            CAPITAL_GAIN,
            EXPECTED_INTERNAL_TRANSFER,
            UNPAIRED_INTERNAL_TRANSFER,
        ])
    )

def totalSaving(transactions: List[Transaction]) -> MultiCurrencyAmount:
    """
    Calculates a subjectively defined savings amount.

    This is supposed to be the earned and deserved amount.
    """
    def includeCategory(c: Category) -> bool:
        if c.isUnder(INCOME): return c.isUnder(EARNED_INCOME)
        return not c.isUnderAny([
            CAPITAL_GAIN,
            EXPECTED_INTERNAL_TRANSFER,
            UNPAIRED_INTERNAL_TRANSFER,
        ])
    return totalAdjustedAmount(
        t for t in transactions
        if not t.isForecast and includeCategory(t.category))

def categoryRespectingNetTotal(trans) -> float:
    return totalAdjustedAmountAsJPY([t for t in earnedIncomesOf(trans) + expensesOf(trans)])

def netWorthReport(allTransactions: List[Transaction]) -> str:
    def generateLines() -> Generator[str, None, None]:
        totals = netWorth(allTransactions)
        totalJPY = totals.aggregatedUsingLatestRatesAs(JPY)
        yield f"Net total JPY using rates today: {totalJPY:.1f} JPY"
        yield "By currency:"
        yield totals.longDescription
    return "\n".join(generateLines())

class SegmentedDisplayOption(Enum):
    """
    Option to display only a segment of income and its corresponding expense.
    Salary: Salary income + Tax and deductions related to salary + All normal expenses
    Bonus: Bonus income + Tax and deductions related to bonus
    Equity: Equity income + Tax related to equity
    """
    NO_SPEC = "Do not specify"
    FOR_SALARY = "For salary"
    FOR_BONUS = "For bonus"
    FOR_SALARY_BONUS = "For salary or bonus"
    FOR_EQUITY = "For equity"
    FOR_CAPITAL_GAIN = "For capital gain"

    def includeTransaction(self, t: Transaction) -> bool:
        Self = SegmentedDisplayOption
        if self == Self.NO_SPEC: return True
        if self == Self.FOR_SALARY:
            if Self.FOR_BONUS.includeTransaction(t): return False
            if Self.FOR_EQUITY.includeTransaction(t): return False
            if Self.FOR_CAPITAL_GAIN.includeTransaction(t): return False
            return True
        if self == Self.FOR_BONUS:
            if t.category.isUnder(BONUS): return True
            if t.category.isUnder(LOCAL_TAX_REPROJECTED_BONUS): return True
            if t.category.isUnder(ESTIMATED_UNPAID_TAX_BONUS): return True
            if t.category.isUnder(WELFARE_BONUS): return True
            if t.category.isUnder(HELATH_INSURANCE_BONUS): return True
            if t.category.isUnder(UNEMPL_INS_BONUS): return True
            if t.category.isUnder(MISC_INCOME_DEDUCTION_BONUS): return True
            if t.category.isUnder(NATIONAL_TAX_WITHHOLDING_BONUS): return True
            return False
        if self == Self.FOR_SALARY_BONUS:
            if Self.FOR_SALARY.includeTransaction(t): return True
            if Self.FOR_BONUS.includeTransaction(t): return True
            return False
        if self == Self.FOR_EQUITY:
            if t.category.isUnder(EQUITY_VESTING): return True
            if t.category.isUnder(NATIONAL_TAX_REPROJECTED_EQUITY): return True
            if t.category.isUnder(LOCAL_TAX_REPROJECTED_EQUITY): return True
            if t.category.isUnder(ESTIMATED_UNPAID_TAX_EQUITY): return True
            # Assume that all saved tax are applied to the "equity part". This is consistent with
            # how tax is segmented: tax for equity is calculated as
            # (tax with all income - tax with all income but equity). However, this only makes sense
            # if the amount of deduction is less than the total of national and local tax for all
            # equity.
            if t.category.isUnder(SAVED_TAX): return True
            if t.category.isUnder(NATIONAL_TAX_PAYMENT): return True
            return False
        if self == Self.FOR_CAPITAL_GAIN:
            if t.category.isUnder(CAPITAL_GAIN): return True
            # TODO: Support tax for capital gain.
            return False
        assert(False)

    def filterTransactions(self, ts: List[Transaction]) -> List[Transaction]:
        return [t for t in ts if self.includeTransaction(t)]

@dataclass
class GroupLabelRange:
    """
    An inclusive range of labels starting from `fromLabel` and ends at `toLabel`.
    Note: there is no checking for validity in the type itself.
    """
    fromLabel: GroupLabel
    toLabel: GroupLabel
    def __str__(self): return f"from {self.fromLabel} to {self.toLabel}"

class LabelSetAlias(Enum):
    """
    An alias for a set of labels, for example, all separate time intervals in 2020.
    """
    MONTHS_2019 = "Months in 2019"
    MONTHS_2020 = "Months in 2020"
    MONTHS_2021 = "Months in 2021"
    MONTHS_2022 = "Months in 2022"
    MONTHS_2023 = "Months in 2023"
    MONTHS_2024 = "Months in 2024"
    MONTHS_2025 = "Months in 2025"
    MONTHS_2025_WITH_ONLY_FORECAST = "Months in 2025 with only forecast"
    MONTHS_FROM_2020 = "Months from 2020"
    ALL_MONTHS = "All Months"
    ALL_YEARS = "All Years"

    def __str__(self): return self.value

    def hasLabel(self, label: GroupLabel, group: List[Transaction]) -> bool:
        # TODO: match months/years in a more robust way
        if self == LabelSetAlias.MONTHS_2019:
            return len(label) == len("YYYY-MM-DD~") and label[:4] == "2019"
        if self == LabelSetAlias.MONTHS_2020:
            return len(label) == len("YYYY-MM-DD~") and label[:4] == "2020"
        if self == LabelSetAlias.MONTHS_2021:
            return len(label) == len("YYYY-MM-DD~") and label[:4] == "2021"
        if self == LabelSetAlias.MONTHS_2022:
            return len(label) == len("YYYY-MM-DD~") and label[:4] == "2022"
        if self == LabelSetAlias.MONTHS_2023:
            return len(label) == len("YYYY-MM-DD~") and label[:4] == "2023"
        if self == LabelSetAlias.MONTHS_2024:
            return len(label) == len("YYYY-MM-DD~") and label[:4] == "2024"
        if self == LabelSetAlias.MONTHS_2025:
            return len(label) == len("YYYY-MM-DD~") and label[:4] == "2025"
        if self == LabelSetAlias.MONTHS_FROM_2020:
            return len(label) == len("YYYY-MM-DD~") and int(label[:4]) >= 2020
        if self == LabelSetAlias.MONTHS_2025_WITH_ONLY_FORECAST:
            return (
                len(label) == len("YYYY-MM-DD~") and
                label[:4] == "2025" and
                len(group) > 1 and
                all(t.isForecast for t in group)
            )
        if self == LabelSetAlias.ALL_MONTHS:
            return len(label) == len("YYYY-MM-DD~")
        if self == LabelSetAlias.ALL_YEARS:
            return len(label) == len("YYYY") and label.isnumeric()
        assert(False)

GroupLabelOption = Union[GroupLabel, GroupLabelRange, LabelSetAlias]

def filterLabelsThatMatchOption(
    labels: List[GroupLabel],
    labelsToGroups: Dict[GroupLabel, List[Transaction]],
    option: Optional[GroupLabelOption]
) -> List[GroupLabel]:
    match option:
        case None: return labels
        case groupLabelOption if type(groupLabelOption) == GroupLabel:
            return [l for l in labels if l == groupLabelOption]
        case GroupLabelRange(fromLabel=fromLabel, toLabel=toLabel):
            includedLabels = []
            collecting = False
            for l in labels:
                if l == fromLabel: collecting = True
                if collecting: includedLabels.append(l)
                if l == toLabel: break
            return includedLabels
        case setAliasOption if type(setAliasOption) == LabelSetAlias:
            includedLabels = [l for l in labels if setAliasOption.hasLabel(l, labelsToGroups[l])]
            return includedLabels
    assert(False)

@dataclass
class AnalysisProviderFilter:
    # --- Transaction filtering options ---
    labelOption: Optional[GroupLabelOption] = None
    descriptionContains: Optional[str] = None
    categoryFilter: Optional[Category] = None
    exactMatchCategory: bool = False
    recordAccount: Optional[Account] = None
    segmentedDisplayOption: SegmentedDisplayOption = SegmentedDisplayOption.NO_SPEC
    amountQuantityFrom: Optional[float] = None
    amountQuantityUntil: Optional[float] = None
    filterByRawAmount: bool = False
    customFilter: Optional[Callable[[Transaction], bool]] = None
    # TODO: Add process options.

    def matchingTransactionsInGroups(
        self,
        labels: List[GroupLabel],
        labelsToGroups: Dict[GroupLabel, List[Transaction]]
    ) -> "OrderedDict[GroupLabel, List[Transaction]]":
        result = OrderedDict()
        includedLabels = filterLabelsThatMatchOption(labels, labelsToGroups, self.labelOption)
        def quantityForFiltering(t: Transaction):
            return t.rawAmount.quantity if self.filterByRawAmount else t.adjustedAmount.quantity
        for label, group in labelsToGroups.items():
            if label not in includedLabels: continue
            selected = group
            if self.categoryFilter is None:
                pass
            elif self.exactMatchCategory:
                selected = [t for t in selected if t.category == self.categoryFilter]
            else:
                selected = [t for t in selected if t.category.isUnder(self.categoryFilter)]
            if self.descriptionContains is not None and len(self.descriptionContains) > 0:
                selected = [t for t in selected if self.descriptionContains in t.description]
            if self.recordAccount is not None:
                selected = [t for t in selected if t.account == self.recordAccount]
            if self.amountQuantityFrom is not None:
                selected = [
                    t for t in selected
                    if quantityForFiltering(t) >= self.amountQuantityFrom
                ]
            if self.amountQuantityUntil is not None:
                selected = [
                    t for t in selected
                    if quantityForFiltering(t) <= self.amountQuantityUntil
                ]
            if self.customFilter is not None:
                selected = [t for t in selected if self.customFilter(t)]
            selected = self.segmentedDisplayOption.filterTransactions(selected)
            result[label] = selected
        return result

    def matchingTransactions(self,
                             labels: List[GroupLabel],
                             labelsToGroups: Dict[GroupLabel, List[Transaction]]
                             ) -> List[Transaction]:
        transactionsInGroups = self.matchingTransactionsInGroups(labels, labelsToGroups)
        merged = []
        for group in transactionsInGroups.values():
            merged += group
        return merged

class CategorizeOption(Enum):
    ORIGINAL = "Use transaction original category"
    ROOT = "Use root categories"
    DEPTH_ONE = "Use categories of depth 1"
    @property
    def transformCategory(self) -> CategoryTransformer:
        Self = CategorizeOption
        if self == Self.ORIGINAL: return lambda c: c
        if self == Self.ROOT: return reduceToAncestorOfDepth(0)
        if self == Self.DEPTH_ONE: return reduceToAncestorOfDepth(1)
        assert(False)
    def transformAnnotatedCategory(self, c: AnnotatedCategory) -> AnnotatedCategory:
        return c.transformCategory(self.transformCategory)

@dataclass
class AnalysisProviderOptions:
    filter: AnalysisProviderFilter
    categorizeOption: CategorizeOption = CategorizeOption.ORIGINAL

@dataclass
class BarChartData:
    labels: List[GroupLabel]
    incomeTotalsByCat: List[Dict[AnnotatedCategory, float]]
    expenseTotalsByCat: List[Dict[AnnotatedCategory, float]]
    orderedCategories: List[AnnotatedCategory]

    @property
    def orderedIncomeCats(self) -> List[AnnotatedCategory]:
        return [ c for c in self.orderedCategories
                 if any(c in d for d in self.incomeTotalsByCat) ]
    @property
    def orderedExpenseCats(self) -> List[AnnotatedCategory]:
        return [ c for c in self.orderedCategories
                 if any(c in d for d in self.expenseTotalsByCat) ]

    def withCategoryTransformed(self, categorizeOption: CategorizeOption) -> "BarChartData":
        def mapKeysMergingValues(catToVals: Dict[AnnotatedCategory, float]):
            merged: Dict[AnnotatedCategory, float] = DefaultDict(float)
            for c in catToVals:
                merged[categorizeOption.transformAnnotatedCategory(c)] += catToVals[c]
            return merged
        def transformedTotals(
            totals: List[Dict[AnnotatedCategory, float]]
        ) -> List[Dict[AnnotatedCategory, float]]:
            return [mapKeysMergingValues(d) for d in totals]
        return BarChartData(
            labels=self.labels,
            incomeTotalsByCat=transformedTotals(self.incomeTotalsByCat),
            expenseTotalsByCat=transformedTotals(self.expenseTotalsByCat),
            orderedCategories=self.orderedCategories
        )

@dataclass
class PieChartData:
    labels: List[GroupLabel]
    categoryToAmount: Dict[AnnotatedCategory, float]
    otherCategoryToAmount: Optional[List[Tuple[AnnotatedCategory, float]]] = None
    isGroupAverage: bool = False

    @property
    def longDescription(self) -> str:
        def generateLines():
            labelsDesc = ", ".join(self.labels)
            yield f"PieChartData for {labelsDesc}:"
            sortedPairs = sorted(
                list(self.categoryToAmount.items()), key=lambda p: p[1], reverse=True)
            others = self.otherCategoryToAmount
            total = sum(am for _, am in sortedPairs)
            def line(cat: AnnotatedCategory, am: float):
                return f"{cat.label}: {am / total:.1%}, {am:,.2f} JPY"
            for cat, am in sortedPairs:
                yield "  " + line(cat, am)
            if others is not None:
                yield ""
                yield f"Under {OTHER.label}:"
                for cat, am in others: yield "    " + line(cat, am)
        return "\n".join(generateLines())

    def withCategoryTransformed(self, categorizeOption: CategorizeOption) -> "PieChartData":
        newCategoryToAmount: Dict[AnnotatedCategory, float] = {}
        for cat, am in self.categoryToAmount.items():
            newCat = categorizeOption.transformAnnotatedCategory(cat)
            newCategoryToAmount[newCat] = newCategoryToAmount.get(newCat, 0.0) + am
        return replace(self, categoryToAmount=newCategoryToAmount)

    def withMinorGroupsAsOther(self) -> "PieChartData":
        pairs = list(self.categoryToAmount.items())
        total = sum(abs(v) for v in self.categoryToAmount.values())
        minorCats = {c for c, am in pairs if abs(am) / total < 0.02}
        minorPairs = [(c, am) for c, am in pairs if c in minorCats and am > 0]
        majorPairs = [(c, am) for c, am in pairs if c not in minorCats]
        totalMinorExpenseAmount = sum((am for _, am in minorPairs), start=0.0)
        resultPairs = majorPairs
        if totalMinorExpenseAmount > 0:
            nonForecastedAmount = sum((am for c, am in minorPairs if not c.isForecast), start=0.0)
            forecastedAmount = sum((am for c, am in minorPairs if c.isForecast), start=0.0)
            resultPairs += [
                (AnnotatedCategory(OTHER, isForecast=False), nonForecastedAmount),
                (AnnotatedCategory(OTHER, isForecast=True), forecastedAmount),
            ]
        newCategoryToAmount: Dict[AnnotatedCategory, float] = {c: am for c, am in resultPairs}
        otherCategoryToAmount = sorted(minorPairs, key=lambda p: abs(p[1]), reverse=True)
        return replace(
            self, categoryToAmount=newCategoryToAmount, otherCategoryToAmount=otherCategoryToAmount)

    def averageByGroup(self) -> "PieChartData":
        if self.isGroupAverage: return self
        numGroups = len(self.labels)
        averagedCategoryToAmount = { c: am / numGroups for c, am in self.categoryToAmount.items() }
        averagedOtherCategoryToAmount = None
        if self.otherCategoryToAmount is not None:
            averagedOtherCategoryToAmount = [
                (c, am / numGroups) for c, am in self.otherCategoryToAmount
            ]
        return replace(
            self,
            categoryToAmount=averagedCategoryToAmount,
            otherCategoryToAmount=averagedOtherCategoryToAmount,
            isGroupAverage=True)

class DeductIncomeOption(Enum):
    """
    Option to deduct certain items from salaray during analysis.
    For example, factoring out welfare and tax withholding.
    """
    NO_DEDUCTION = "No deduction"
    DEDUCT_SOCIAL_SECURITY = "Deduct payslip non-tax items"
    DEDUCT_SOCIAL_SECURITY_AND_PAID_TAX = "Deduct payslip items and paid tax"
    DEDUCT_SOCIAL_SECURITY_AND_ALL_TAX = "Deduct payslip items and all (paid & unpaid) tax"
    DEDUCT_SOCIAL_SECURITY_AND_ALL_TAX_AND_RENT = \
        "Deduct payslip items, all (paid & unpaid) tax and rent"

    @property
    def targetIncomeCategoryFromExpenseAncestor(self) -> Dict[Category, Category]:
        DictToReturn = Dict[Category, Category]
        def mergeDicts(d1: DictToReturn, d2: DictToReturn) -> DictToReturn: # type: ignore
            result = { k: v for k, v in d1.items() }
            for k, v in d2.items(): result[k] = v
            return result
        Self = DeductIncomeOption
        if self == Self.NO_DEDUCTION: return {}
        if self == Self.DEDUCT_SOCIAL_SECURITY:
            return {
                WELFARE_SALARY:               SALARY,
                HELATH_INSURANCE_SALARY:      SALARY,
                UNEMPL_INS_SALARY:            SALARY,
                MISC_INCOME_DEDUCTION_SALARY: SALARY,
                WELFARE_BONUS:                BONUS,
                HELATH_INSURANCE_BONUS:       BONUS,
                UNEMPL_INS_BONUS:             BONUS,
                MISC_INCOME_DEDUCTION_BONUS:  BONUS
            }
        if self == Self.DEDUCT_SOCIAL_SECURITY_AND_PAID_TAX:
            return mergeDicts(
                Self.DEDUCT_SOCIAL_SECURITY.targetIncomeCategoryFromExpenseAncestor, {
                    NATIONAL_TAX_WITHHOLDING_SALARY: SALARY,
                    LOCAL_TAX_REPROJECTED_SALARY:    SALARY,
                    NATIONAL_TAX_WITHHOLDING_BONUS:  BONUS,
                    LOCAL_TAX_REPROJECTED_BONUS:     BONUS,
                    NATIONAL_TAX_REPROJECTED_EQUITY: EQUITY_VESTING,
                    LOCAL_TAX_REPROJECTED_EQUITY:    EQUITY_VESTING,
                    NATIONAL_TAX_PAYMENT:            EQUITY_VESTING,
                    # Assuming it only covers the equity part of income, even though it might be
                    # inaccurate.
                    SAVED_TAX:                       EQUITY_VESTING,
                })
        if self == Self.DEDUCT_SOCIAL_SECURITY_AND_ALL_TAX:
            return mergeDicts(
                Self.DEDUCT_SOCIAL_SECURITY_AND_PAID_TAX.targetIncomeCategoryFromExpenseAncestor, {
                    ESTIMATED_UNPAID_TAX_SALARY:     SALARY,
                    ESTIMATED_UNPAID_TAX_BONUS:      BONUS,
                    ESTIMATED_UNPAID_TAX_EQUITY:     EQUITY_VESTING,
                })
        if self == Self.DEDUCT_SOCIAL_SECURITY_AND_ALL_TAX_AND_RENT:
            return mergeDicts(
                Self.DEDUCT_SOCIAL_SECURITY_AND_ALL_TAX.targetIncomeCategoryFromExpenseAncestor, {
                    RENT: SALARY
                })
        assert(False)

    @property
    def categoriesToDeductGroupedByTargets(self) -> Dict[Category, Set[Category]]:
        ancestorsToTargets = self.targetIncomeCategoryFromExpenseAncestor
        result = {}
        for cat, target in ancestorsToTargets.items():
            result[target] = result.get(target, set()) | { cat }
        return result

    def deductOps(self, expenseTotals: Dict[Category, float]) -> Dict[Category, Tuple[Set[Category], float]]:
        targetsFromAncestors = self.targetIncomeCategoryFromExpenseAncestor
        def ancestorFor(cat: Category) -> Optional[Category]:
            for ancestor in targetsFromAncestors.keys():
                if cat.isUnder(ancestor): return ancestor
            return None
        ops: Dict[Category, Tuple[Set[Category], float]] = {}
        for cat in expenseTotals.keys():
            ancestor = ancestorFor(cat)
            if ancestor is None: continue
            target = targetsFromAncestors[ancestor]
            catSet, total = ops.get(target, (set(), 0.0))
            ops[target] = (catSet | { cat }, total + expenseTotals[cat])
        return ops

    def applyDeductionForBarChart(self, barChartData: BarChartData):
        def applyToTotals(
            incomeTotals: Dict[AnnotatedCategory, float],
            expenseTotals: Dict[AnnotatedCategory, float]
        ):
            def makeDeductOps(isForecast: bool):
                exps = {
                    ac.category : t
                    for ac, t in expenseTotals.items() if ac.isForecast == isForecast
                }
                return self.deductOps(exps)
            nonForecastDeductOps = makeDeductOps(isForecast=False)
            forecastDeductOps = makeDeductOps(isForecast=True)

            def shouldSkip(isForecast: bool):
                deductOps = forecastDeductOps if isForecast else nonForecastDeductOps
                targets = deductOps.keys()
                def hasEnoughIncomeFor(target: Category) -> bool:
                    _, totalDeduction = deductOps[target]
                    annotatedTarget = AnnotatedCategory(target, isForecast)
                    return incomeTotals.get(annotatedTarget, 0.0) >= totalDeduction
                # Do not apply any deduction if there is not enough income to cover expense to
                # deduct.
                return any(not hasEnoughIncomeFor(t) for t in targets)
            if shouldSkip(isForecast=True): return
            if shouldSkip(isForecast=False): return

            oldToNewTarget = { SALARY: SALARY_AFTER_DEDUCTION,
                               BONUS: BONUS_AFTER_DEDUCTION,
                               EQUITY_VESTING: EQUITY_AFTER_DEDUCTION }
            def applyOps(isForecast: bool):
                def annotated(cat: Category): return AnnotatedCategory(cat, isForecast)
                deductOps = forecastDeductOps if isForecast else nonForecastDeductOps
                for target in deductOps:
                    catSet, amount = deductOps[target]
                    for cat in catSet: expenseTotals.pop(annotated(cat))
                    if annotated(target) not in incomeTotals:
                        import rich
                        rich.print(f"{isForecast=}")
                        rich.print(f"{target=}")
                        rich.print("incomeTotals:", incomeTotals)
                        rich.print("deductOps:", deductOps)
                    annotatedNewTarget = annotated(oldToNewTarget[target])
                    incomeTotals[annotatedNewTarget] = incomeTotals.pop(annotated(target)) - amount
            applyOps(isForecast=True)
            applyOps(isForecast=False)
        for incs, exps in zip(barChartData.incomeTotalsByCat, barChartData.expenseTotalsByCat):
            applyToTotals(incs, exps)

    def applyDeductionForPieChart(self, pieChartData: PieChartData):
        def apply(isForecast: bool):
            def annotated(cat: Category): return AnnotatedCategory(cat, isForecast)
            plainCategoryToAmount = {
                ac.category: am
                for ac, am in pieChartData.categoryToAmount.items()
                if ac.isForecast == isForecast
            }
            deductOps = self.deductOps(plainCategoryToAmount)
            for catSet, _ in deductOps.values():
                for cat in catSet: pieChartData.categoryToAmount.pop(annotated(cat))
        apply(isForecast=True)
        apply(isForecast=False)

@dataclass
class AnalysisProvider:
    labelsToGroups: Dict[GroupLabel, List[Transaction]]
    labels: List[GroupLabel]
    categories: List[AnnotatedCategory]
    rates: RetrivedRates

    def __init__(self, transactions: List[Transaction]):
        salarySectionedGroups, _ = splitIntoTimeSectionsBySalaryIncome(transactions)
        if len(salarySectionedGroups) > 0:
            lastSalarySection = salarySectionedGroups.pop()
            minDate, maxDate = minMaxDateOf(lastSalarySection)
            if (maxDate - minDate).days > 60:
                cutoffDate = minDate + timedelta(days=30)
                salarySectionedGroups.append([t for t in lastSalarySection if t.date < cutoffDate])
                salarySectionedGroups.append([t for t in lastSalarySection if t.date >= cutoffDate])
        def salarySectionedGroupLabel(trans):
            minDate, _ = minMaxDateOf(trans)
            return f"{minDate}~"
        years = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
        self.labels = (
            ["All"] +
            [str(year) for year in years] +
            [salarySectionedGroupLabel(g) for g in salarySectionedGroups]
        )
        self.labelsToGroups = {salarySectionedGroupLabel(g): g for g in salarySectionedGroups}
        self.labelsToGroups["All"] = transactions
        for year in years:
            self.labelsToGroups[str(year)] = [t for t in transactions if t.date.year == year]
        allCategories = ORDERED_BASE_CATEGORIES + cast(List[Category], ORDERED_PSEUDO_CATEGORIES)
        reorderedCategories = reorderCategories(
            list(allCategories),
            leading=[RENT, TAX, SOCIAL_SECURITY, MAJOR_SHOPPING,
                     DAILY_SHOPPING, UTILITY_BILL,
                     SALARY_AFTER_DEDUCTION],
                     trailing=[REMAINING])
        self.categories = (
            [AnnotatedCategory(c, isForecast=False) for c in reorderedCategories] +
            [AnnotatedCategory(c, isForecast=True) for c in reorderedCategories]
        )
        self.rates = getOrRetrieveLatestRates()

    def matchingTransactions(self, options: AnalysisProviderOptions) -> List[Transaction]:
        return options.filter.matchingTransactions(self.labels, self.labelsToGroups)

    def groupedMatchingTransactions(self, options: AnalysisProviderOptions):
        return options.filter.matchingTransactionsInGroups(
            self.labels, self.labelsToGroups)

    def transactionSetStatsMatching(self, options: AnalysisProviderOptions):
        return TransactionSetStats(self.matchingTransactions(options))

    def groupOverview(self, label: GroupLabel) -> str:
        options = AnalysisProviderOptions(filter=AnalysisProviderFilter(labelOption=label))
        transactions = self.matchingTransactions(options)
        return transactionsOverview(label, transactions)

    def netTotalsReport(self) -> str:
        return netWorthReport(self.labelsToGroups["All"])

    def barChartData(self, options: AnalysisProviderOptions,
                     deductSalaryOption: DeductIncomeOption) -> BarChartData:
        matchedInGroups = options.filter.matchingTransactionsInGroups(self.labels, self.labelsToGroups)
        includedLabels = list(matchedInGroups.keys())
        groups = [matchedInGroups[l] for l in includedLabels]
        def totalsOf(groups: List[List[Transaction]], isExpense: bool):
            filterFn = expensesOf if isExpense else earnedIncomesOf
            filteredGroups = [filterFn(g) for g in groups]
            stats = [TransactionSetStats(g) for g in filteredGroups]
            return [s.categorizedTotalsAsJPY(absVals=isExpense) for s in stats]
        barChartData = BarChartData(
            labels=includedLabels,
            incomeTotalsByCat=totalsOf(groups, isExpense=False),
            expenseTotalsByCat=totalsOf(groups, isExpense=True),
            orderedCategories=self.categories)
        deductSalaryOption.applyDeductionForBarChart(barChartData)
        return barChartData.withCategoryTransformed(options.categorizeOption)

    def pieChartData(self,
                     options: AnalysisProviderOptions,
                     deductIncomeOption: DeductIncomeOption,
                     includeRemaining: bool,
                     averageByGroup: bool) -> Optional[PieChartData]:
        groupedMatchingTrans = self.groupedMatchingTransactions(options)
        labels = list(groupedMatchingTrans.keys())
        stats = TransactionSetStats(list(itertools.chain(*groupedMatchingTrans.values())))
        catToAmount = stats.expenseSummary(includeRemaining).amountsByCategory
        if len(catToAmount) == 0: return None
        pieChartData = PieChartData(labels=labels, categoryToAmount=catToAmount)
        deductIncomeOption.applyDeductionForPieChart(pieChartData)
        pieChartData = pieChartData.withCategoryTransformed(options.categorizeOption)
        pieChartData = pieChartData.withMinorGroupsAsOther()
        if averageByGroup: pieChartData = pieChartData.averageByGroup()
        return pieChartData

    def dataForShopDistribution(self,
                                options: AnalysisProviderOptions,
                                deductIncomeOption: DeductIncomeOption) -> List[Tuple[str, float]]:
        selectedTrans = self.matchingTransactions(options)
        selectedTrans = [t for t in selectedTrans if t.category.isUnder(EXPENSE)]
        selectedTrans = [t for t in selectedTrans if "口座振替" not in t.description]
        categories = { t.category for t in selectedTrans }
        ancestorsToExclude = set()
        for ancestors in deductIncomeOption.categoriesToDeductGroupedByTargets.values():
            ancestorsToExclude |= ancestors
        categoriesToExclude = { cat for cat in categories if any(cat.isUnder(a) for a in ancestorsToExclude) }
        selectedTrans = [t for t in selectedTrans if t.category not in categoriesToExclude]
        def shopNameOfTrans(t: Transaction) -> str:
            if t.category.isUnder(TAX): return "Tax office"
            if t.category.isUnder(RENT): return "Rent"
            if "ヨドバシカメラ" in t.description: return "Yodobashi"
            if "ﾖﾄﾞﾊﾞｼｶﾒﾗ" in t.description: return "Yodobashi"
            if "ムジルシリヨウヒン" in t.description: return "MUJI"
            if "無印良品" in t.description: return "MUJI"
            if "ＭＵＪＩ" in t.description: return "MUJI"
            if "セブン－イレブン" in t.description: return "7-ELEVEN"
            if "ファミリーマート" in t.description: return "FamilyMart"
            if "ローソン" in t.description: return "Lawson"
            if "Ａｐｐｌｅ　Ｓｔｏｒｅ" in t.description: return "Apple Store"
            if "Ａｐｐｌｅ  Ｓｔｏｒｅ" in t.description: return "Apple Store"
            if "東京電力" in t.description: return "東京電力"
            if isTaxi(t): return "Taxi"
            if isMenu(t): return "Menu"
            if isUberEats(t): return "Uber Eats"
            if isAmazon(t): return "Amazon"
            return t.description
        namesToTotals: dict = {}
        for t in selectedTrans:
            name = shopNameOfTrans(t)
            namesToTotals[name] = namesToTotals.get(name, 0) + abs(t.adjustedAmount.quantity)
        return sorted(namesToTotals.items(), key=lambda x: x[1], reverse=True)
