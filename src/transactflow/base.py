import csv
from functools import reduce
from inspect import currentframe, getframeinfo
import io
import os
from types import FrameType
from typing import Callable, Dict, Hashable, Iterable, Iterator, List, NamedTuple, Tuple, Optional, NewType, TypeVar, Union
from termcolor import colored
from datetime import date
from dataclasses import dataclass, field, replace

__all__ = [
    # Type aliases
    "Account", "Date", "Currency",

    # Currency constants
    "JPY", "USD", "CNY", "STOCK_UNIT", "EMPTY_CURRENCY",

    # Account constants
    "ORDERED_ACCOUNTS",
    "EMPLOYER", "FAMILY", "OTHER_INCOME_SOURCE",
    "GENERAL_EXPENSE_DESTINATION", "SMBC_PRESTIA", "AU_JIBUN", "SBI_NET_BANK",
    "JCB_CREDIT_CARD", "SMBC_CREDIT_CARD", "AMEX_JP", "DINERS_CLUB",
    "REVOLUT", "KYASH", "AMAZON_GIFT_CARD", "MORGAN_STANLEY", "PENSION",
    "PSEUDO_ACCOUNT", "CASH", "MOBILE_SUICA",

    # Category
    "Category", "ORDERED_BASE_CATEGORIES", "verifyCategoryLabelsUnique",
    "EXPENSE", "RENT", "SOCIAL_SECURITY", "HEALTH_INSURANCE",
    "HEALTH_INSURANCE_SALARY", "HEALTH_INSURANCE_BONUS",
    "WELFARE", "WELFARE_SALARY", "WELFARE_SALARY_FORECAST", "WELFARE_BONUS",
    "UNEMPL_INS", "UNEMPL_INS_SALARY", "UNEMPL_INS_BONUS",
    "MISC_INCOME_DEDUCTION", "MISC_INCOME_DEDUCTION_SALARY", "MISC_INCOME_DEDUCTION_BONUS",
    "TAX", "CHARGED_TAX",
    "NATIONAL_TAX_WITHHOLDING", "NATIONAL_TAX_WITHHOLDING_SALARY", "NATIONAL_TAX_WITHHOLDING_BONUS",
    "NATIONAL_TAX_PREPAYMENT", "NATIONAL_TAX_PAYMENT", "NATIONAL_TAX_REPROJECTED",
    "FURUSATO_DONATION", "NATIONAL_TAX_REPROJECTED_EQUITY",
    "LOCAL_TAX_DEDUCTION", "LOCAL_TAX_PAYMENT", "LOCAL_TAX_REPROJECTED",
    "LOCAL_TAX_REPROJECTED_SALARY", "LOCAL_TAX_REPROJECTED_BONUS", "LOCAL_TAX_REPROJECTED_EQUITY",
    "ESTIMATED_UNPAID_TAX", "ESTIMATED_UNPAID_TAX_SALARY",
    "ESTIMATED_UNPAID_TAX_BONUS", "ESTIMATED_UNPAID_TAX_EQUITY",
    "SAVED_TAX", "SAVED_TAX_FROM_FURUSATO_DONATION",
    "SAVED_TAX_FROM_DEPENDENT_TRANSFER", "SAVED_TAX_FROM_RENT",
    "HOME_INSURANCE", "UTILITY_BILL", "SHOPPING", "DAILY_SHOPPING", "MAJOR_SHOPPING",
    "DAILY_PUBLIC_TRANSPORT", "TAXI", "FOOD_DRINK_OUTSIDE", "CASH_OUT",
    "MEDICAL", "ENTERTAINMENT", "EDUCATION", "TRAVEL", "DIGITAL_SERVICE", "DEPENDENT_TRANSFER",
    "INCOME", "EARNED_INCOME", "SALARY", "SALARY_FORECAST",
    "NON_TAXABLE_SALARY", "NON_TAXABLE_SALARY_HOUSING_BENEFIT",
    "BONUS", "EQUITY_VESTING", "BANK_INTEREST", "CASH_BACK", "CAPITAL_GAIN",
    "REFUND_REIMBURSEMENT", "EXCLUDED_INCOME", "PENSION_CONTRIBUTION",
    "INTERNAL_TRANSFER", "UNPAIRED_INTERNAL_TRANSFER", "EXPECTED_INTERNAL_TRANSFER",
    "CURRENCY_CONVERSION_SENT", "CURRENCY_CONVERSION_RECEIVED", "SOURCE_CUTOFF",

    # Color
    "RGBColor", "ColorSpec",
    "HTML_EXPENSE_COLOR", "HTML_INCOME_COLOR", "IRRELEVANT_COLOR_CODE",
    "colorCodeForJPYAmount",

    # MoneyAmount
    "formatQuantity", "MoneyAmount", "amountDeltaIsNegligible", "EMPTY_AMOUNT",
    "amountsHaveSameCurrency", "sumSingleCurrencyAmounts", "SegmentedTotals",

    # ExchangeRates
    "ExchangeRates", "EMPTY_EXCHANGE_RATES",

    # Transaction
    "Transaction", "syntheticTransaction",
    "simpleCSVForTransaction", "sumSingleCurrencyAdjustedAmounts",
    "printTransactionsAsCSV", "splitTransactions",
    "sourceLocationFromFrame", "makeSourceLocation", "makeManualTransactionFn",
    "isMainSalaryIncome", "sortedByDate",
    "splitIntoTimeSectionsBySalaryIncome", "minMaxDateOf",
    "earnedIncomesOf", "expensesOf",

    # Utilities
    "memo", "concat", "groupAsDict", "popFirstMatch", "mapOptional",
]

Account = str
Date = date

ORDERED_ACCOUNTS = [
    EMPLOYER := "Employer",
    FAMILY := "Family",
    OTHER_INCOME_SOURCE := "Other income source",

    GENERAL_EXPENSE_DESTINATION := "Expense Destination",
    SMBC_PRESTIA := "SMBC Prestia",
    AU_JIBUN := "AU Jibun Bank",
    SBI_NET_BANK := "SBI Net Bank",
    JCB_CREDIT_CARD := "JCB Credit Card",
    SMBC_CREDIT_CARD := "SMBC Credit Card",
    AMEX_JP := "AMEX JP",
    DINERS_CLUB := "Diners Club",
    REVOLUT := "Revolut",
    KYASH := "Kyash",
    AMAZON_GIFT_CARD := "Amazon Gift Card",
    MORGAN_STANLEY := "Morgan Stanley",
    PENSION := "Pension",

    PSEUDO_ACCOUNT := "Pseudo account",
]

# Cash expense is not being recorded for now
CASH = GENERAL_EXPENSE_DESTINATION
# Mobile Suica expense is not being recorded for now
MOBILE_SUICA = GENERAL_EXPENSE_DESTINATION

@dataclass
class Category:
    label: str
    parent: Optional["Category"] = None
    
    def __hash__(self):
        return hash(self.label)

    def __eq__(self, other):
        if other == None: return False
        return self.label == other.label

    def __repr__(self):
        return f"<Category: {self.label}>"

    def isUnder(self, ancestor: "Category"):
        curr = self
        while curr != None:
            if curr == ancestor:
                return True
            else:
                curr = curr.parent
        return False

    def isUnderAny(self, ancestors: Iterable["Category"]):
        return any(self.isUnder(a) for a in ancestors)

    def ancestorBy(self, lvl: int) -> "Category":
        if lvl == 0: return self
        if self.parent is None: return self
        return self.parent.ancestorBy(lvl - 1)

    @property
    def depth(self) -> int:
        if self.parent is None: return 0
        return self.parent.depth + 1

ORDERED_BASE_CATEGORIES = [
    EXPENSE := Category("General Expense"),

    RENT := Category("Rent", parent=EXPENSE),
    SOCIAL_SECURITY := Category("Social security", parent=EXPENSE),
    HEALTH_INSURANCE := Category("Health Insurance", parent=SOCIAL_SECURITY),
    HEALTH_INSURANCE_SALARY := Category("Health Insurance for Salary", parent=HEALTH_INSURANCE),
    HEALTH_INSURANCE_BONUS := Category("Health Insurance for Bonus", parent=HEALTH_INSURANCE),
    WELFARE := Category("Welfare", parent=SOCIAL_SECURITY),
    WELFARE_SALARY := Category("Welfare for Salary", parent=WELFARE),
    WELFARE_SALARY_FORECAST := Category("Welfare for Salary (forecast)", parent=WELFARE),
    WELFARE_BONUS := Category("Welfare for Bonus", parent=WELFARE),
    UNEMPL_INS := Category("Unempl Ins", parent=SOCIAL_SECURITY),
    UNEMPL_INS_SALARY := Category("Unempl Ins for Salary", parent=UNEMPL_INS),
    UNEMPL_INS_BONUS := Category("Unempl Ins for Bonus", parent=UNEMPL_INS),
    MISC_INCOME_DEDUCTION := Category("Misc Income Deduction", parent=EXPENSE),
    MISC_INCOME_DEDUCTION_SALARY := Category("Misc income deduction for Salary", parent=MISC_INCOME_DEDUCTION),
    MISC_INCOME_DEDUCTION_BONUS := Category("Misc income deduction for Bonus", parent=MISC_INCOME_DEDUCTION),

    TAX := Category("Tax", parent=EXPENSE),
    CHARGED_TAX := Category("Charged Tax", parent=TAX),
    NATIONAL_TAX_WITHHOLDING := Category("National tax withholding", parent=CHARGED_TAX),
    NATIONAL_TAX_WITHHOLDING_SALARY := Category("National tax withholding for salary", parent=NATIONAL_TAX_WITHHOLDING),
    NATIONAL_TAX_WITHHOLDING_BONUS := Category("National tax withholding for bonus", parent=NATIONAL_TAX_WITHHOLDING),
    NATIONAL_TAX_PREPAYMENT := Category("National tax prepayment", parent=CHARGED_TAX),
    NATIONAL_TAX_PAYMENT := Category("National tax payment", parent=CHARGED_TAX),
    NATIONAL_TAX_REPROJECTED := Category("National tax reprojected", parent=CHARGED_TAX),
    # These two shouldn't exist(?) with tax withholding and year end adjustment
    # NATIONAL_TAX_REPROJECTED_SALARY := Category("National tax reprojected for salary", parent=NATIONAL_TAX_REPROJECTED),
    # NATIONAL_TAX_REPROJECTED_BONUS := Category("National tax reprojected for bonus", parent=NATIONAL_TAX_REPROJECTED),
    FURUSATO_DONATION := Category("Furusato donation", parent=CHARGED_TAX),
    NATIONAL_TAX_REPROJECTED_EQUITY := Category("National tax reprojected for equity", parent=NATIONAL_TAX_REPROJECTED),
    LOCAL_TAX_DEDUCTION := Category("Local tax deduction", parent=CHARGED_TAX),
    LOCAL_TAX_PAYMENT := Category("Local tax payment", parent=CHARGED_TAX),
    LOCAL_TAX_REPROJECTED := Category("Local tax reprojected", parent=CHARGED_TAX),
    LOCAL_TAX_REPROJECTED_SALARY := Category("Local tax reprojected for salary", parent=LOCAL_TAX_REPROJECTED),
    LOCAL_TAX_REPROJECTED_BONUS := Category("Local tax reprojected for bonus", parent=LOCAL_TAX_REPROJECTED),
    LOCAL_TAX_REPROJECTED_EQUITY := Category("Local tax reprojected for equity", parent=LOCAL_TAX_REPROJECTED),
    ESTIMATED_UNPAID_TAX := Category("Estimated Unpaid Tax", parent=TAX),
    ESTIMATED_UNPAID_TAX_SALARY := Category("Estimated Unpaid Tax for Salary", parent=ESTIMATED_UNPAID_TAX),
    ESTIMATED_UNPAID_TAX_BONUS := Category("Estimated Unpaid Tax for Bonus", parent=ESTIMATED_UNPAID_TAX),
    ESTIMATED_UNPAID_TAX_EQUITY := Category("Estimated Unpaid Tax for Equity", parent=ESTIMATED_UNPAID_TAX),
    # TODO: Split savings for national and local tax.
    SAVED_TAX := Category("Saved Tax", parent=TAX),
    SAVED_TAX_FROM_FURUSATO_DONATION := Category("Saved tax from Furusato donation", parent=SAVED_TAX),
    SAVED_TAX_FROM_DEPENDENT_TRANSFER := Category("Saved tax from dependent transfer", parent=SAVED_TAX),
    SAVED_TAX_FROM_RENT := Category("Saved tax from rent", parent=SAVED_TAX),

    HOME_INSURANCE := Category("Home Insurance", parent=EXPENSE),
    UTILITY_BILL := Category("Utility Bill", parent=EXPENSE),
    SHOPPING := Category("Shopping", parent=EXPENSE),
    DAILY_SHOPPING := Category("Daily Shopping", parent=SHOPPING),
    MAJOR_SHOPPING := Category("Major Shopping", parent=SHOPPING),
    DAILY_PUBLIC_TRANSPORT := Category("Daily Public Transport", parent=EXPENSE),
    TAXI := Category("Taxi", parent=EXPENSE),
    FOOD_DRINK_OUTSIDE := Category("Food/Drink Outside", parent=EXPENSE),
    CASH_OUT := Category("Cash Out", parent=EXPENSE),
    MEDICAL := Category("Medical", parent=EXPENSE),
    ENTERTAINMENT := Category("Entertainment", parent=EXPENSE),
    EDUCATION := Category("Education", parent=EXPENSE),
    TRAVEL := Category("Travel", parent=EXPENSE),
    DIGITAL_SERVICE := Category("Digital Service", parent=EXPENSE),
    DEPENDENT_TRANSFER := Category("Dependent Transfer", parent=EXPENSE),

    INCOME := Category("Income"),
    EARNED_INCOME := Category("Earned Income", parent=INCOME),
    SALARY := Category("Salary", parent=EARNED_INCOME),
    SALARY_FORECAST := Category("Salary Forecast", parent=EARNED_INCOME),
    NON_TAXABLE_SALARY := Category("Non-Taxable Salary", parent=SALARY),
    NON_TAXABLE_SALARY_HOUSING_BENEFIT := Category("Non-Taxable Salary - housingBenefit", parent=NON_TAXABLE_SALARY),
    BONUS := Category("Bonus", parent=EARNED_INCOME),
    EQUITY_VESTING := Category("Equity vesting", parent=EARNED_INCOME),
    BANK_INTEREST := Category("Bank Interest", parent=EARNED_INCOME),
    CASH_BACK := Category("Cashback", parent=EARNED_INCOME),
    CAPITAL_GAIN := Category("Capital Gain", parent=EARNED_INCOME),
    REFUND_REIMBURSEMENT := Category("Refund/Reimbursement", parent=EARNED_INCOME),
    EXCLUDED_INCOME := Category("Not Really Income", parent=INCOME),
    PENSION_CONTRIBUTION := Category("Pension contribution", parent=EXCLUDED_INCOME),

    INTERNAL_TRANSFER := Category("Internal Transfer"),
    UNPAIRED_INTERNAL_TRANSFER := Category("Unpaired Internal Transfer"),
    EXPECTED_INTERNAL_TRANSFER := Category("Expected Internal Transfer"),
    CURRENCY_CONVERSION_SENT := Category("Currency conversion (sent)"),
    CURRENCY_CONVERSION_RECEIVED := Category("Currency conversion (received)"),
    SOURCE_CUTOFF := Category("Source cutoff"),
]

def verifyCategoryLabelsUnique():
    labels = set()
    for c in ORDERED_BASE_CATEGORIES:
        if c.label in labels:
            print(f"Found duplicated category label: {c.label}")
            assert(False)
        labels.add(c.label)
verifyCategoryLabelsUnique()

@dataclass(frozen=True)
class RGBColor: r: int; g: int; b: int

@dataclass(frozen=True)
class ColorSpec: max: float; color: RGBColor

HTML_EXPENSE_COLOR = ColorSpec(max=1000000, color=RGBColor(255, 163, 136))
HTML_INCOME_COLOR = ColorSpec(max=500000, color=RGBColor(146, 255, 149))
IRRELEVANT_COLOR_CODE = "rgba(200, 200, 200, 0.5)"

def colorCodeForJPYAmount(amount: float):
    if amount > 0:
        c = HTML_INCOME_COLOR.color
        a = amount / HTML_EXPENSE_COLOR.max
        a = min(a, 1.0)
        return f"rgba({c.r}, {c.g}, {c.b}, {a})"
    else:
        c = HTML_EXPENSE_COLOR.color
        a = (abs(amount) / abs(HTML_EXPENSE_COLOR.max)) * 3
        a = min(a, 1.0)
        return f"rgba({c.r}, {c.g}, {c.b}, {a})"

Currency = NewType("Currency", str)
JPY = Currency("JPY")
USD = Currency("USD")
CNY = Currency("CNY")
STOCK_UNIT = Currency("STOCK_UNIT")
EMPTY_CURRENCY = Currency("Empty Currency")

def formatQuantity(quantity: float) -> str:
    return f"{quantity:.4f}".rstrip("0").rstrip(".")

@dataclass(frozen=True)
class MoneyAmount:
    currency: Currency
    quantity: float

    def __str__(self):
        return f"{formatQuantity(self.quantity)} {self.currency}"

    def __add__(self, other: "MoneyAmount"):
        if self.currency == EMPTY_CURRENCY: return other
        if other.currency == EMPTY_CURRENCY: return self
        assert(self.currency == other.currency)
        return MoneyAmount(self.currency, self.quantity + other.quantity)

    def __sub__(self, other: "MoneyAmount"):
        return self + (-other)

    def __mul__(self, other: float):
        return MoneyAmount(self.currency, self.quantity * other)

    def __truediv__(self, other: float):
        return MoneyAmount(self.currency, self.quantity / other)

    def __abs__(self):
        return MoneyAmount(self.currency, abs(self.quantity))

    def __neg__(self):
        return MoneyAmount(self.currency, -self.quantity)

    def __eq__(self, other: object) -> bool:
        match other:
            case MoneyAmount(_, 0): return self.quantity == 0
            case MoneyAmount(self.currency, self.quantity): return True
            case _: return False

def amountDeltaIsNegligible(delta: MoneyAmount) -> bool:
    if delta.currency == JPY:
        if abs(delta.quantity) > 100: return False
    elif delta.currency == USD:
        if abs(delta.quantity) > 1: return False
    elif delta.currency == STOCK_UNIT:
        if abs(delta.quantity) > 0.1: return False
    elif abs(delta.quantity) > 0: return False
    return True

EMPTY_AMOUNT = MoneyAmount(EMPTY_CURRENCY, 0)

def amountsHaveSameCurrency(amounts: Iterable[MoneyAmount]) -> bool:
    if len(list(amounts)) == 0: return True
    return len(set(am.currency for am in amounts if am != EMPTY_AMOUNT)) == 1

def sumSingleCurrencyAmounts(amounts: Iterable[MoneyAmount]) -> MoneyAmount:
    return reduce(lambda a, b: a + b, amounts, EMPTY_AMOUNT)

class SegmentedTotals(NamedTuple):
    currency: Currency
    forSalary: float
    forBonus: float
    forEquity: float
    forAll: float
    def __post_init__(self):
        assert(self.forSalary + self.forBonus + self.forEquity == self.forAll)
    @property
    def salaryOfAllRatio(self) -> float:
        return 1.0 - self.bonusOfAllRatio - self.equityOfAllRatio
    @property
    def bonusOfAllRatio(self) -> float:
        return float(self.forBonus / self.forAll)
    @property
    def equityOfAllRatio(self) -> float:
        return float(self.forEquity / self.forAll)
    def applyingRatiosToAmountForAll(self, amount: MoneyAmount) -> "SegmentedTotals":
        forSalary = self.forSalary * self.salaryOfAllRatio
        forBonus = self.forBonus * self.bonusOfAllRatio
        return SegmentedTotals(currency=amount.currency,
                               forSalary=forSalary,
                               forBonus=forBonus,
                               forEquity=amount.quantity - forSalary - forBonus,
                               forAll=amount.quantity)

@dataclass(frozen=True)
class ExchangeRates:
    USDJPYRate: Optional[float] = None
    USDPerStockUnitShare: Optional[float] = None
    @property
    def isEmpty(self): return self == EMPTY_EXCHANGE_RATES

EMPTY_EXCHANGE_RATES = ExchangeRates()

@dataclass(frozen=True)
class Transaction:
    """
    A transaction from one account to another.

    Positive amount indicates income, negative for expense. For example,
    amount = 50000 and relatedTo = "SMBC" means this is a transaction of
    50000 JPY from account "SMBC".
    """
    date: Date
    description: str

    rawAmount: MoneyAmount
    """
    The original money amount of transaction. Expected to be consistent with account balance.
    """

    account: Account
    rawRecord: str
    sourceLocation: Optional[Tuple[str, int]]
    category: Category

    # Extension properties: not all transactions have them.
    relatedTo: Optional[Account] = None
    adjustments: Tuple[float, ...] = field(default_factory=lambda: ())
    comment: Optional[str] = None
    referencedExchangeRates: ExchangeRates = EMPTY_EXCHANGE_RATES
    isUnrealized: bool = False
    isForecast: bool = False

    @property
    def adjustedAmount(self) -> MoneyAmount:
        return MoneyAmount(self.rawAmount.currency,
                           self.rawAmount.quantity + sum(am for am in self.adjustments))

    def __post_init__(self):
        if self.isUnrealized: assert(self.rawAmount.quantity == 0)
        if self.isForecast: assert(self.rawAmount.quantity == 0)

    def replacingAccount(self, account: Account): return replace(self, account=account)
    def replacingCategory(self, category: Category):
        # if category.depth <= self.category.depth:
        #     print(self.category, category)
        #     breakpoint()
        return replace(self, category=category)
    def replacingRelatedTo(self, relatedTo: Account):
        if relatedTo is None:
            print(self.relatedTo, relatedTo)
            breakpoint()
        return replace(self, relatedTo=relatedTo)
    def replacingDescription(self, description: str): return replace(self, description=description)
    def replacingComment(self, comment: str): return replace(self, comment=comment)

    def addingAdjustment(self, amount: float):
        return replace(self, adjustments=tuple(list(self.adjustments) + [amount]))

    def __str__(self) -> str:
        quantity = self.adjustedAmount.quantity
        absQuantity = abs(quantity)
        quantityArrow = f"<-({absQuantity:10.1f})--" if quantity >= 0 else \
                        f"--({absQuantity:10.1f})->"
        if self.category == None:
            amountText = quantityArrow
        elif self.category.isUnder(EXPENSE):
            amountText = colored(quantityArrow, "red")
        elif self.category.isUnder(EXCLUDED_INCOME):
            amountText = colored(quantityArrow, "green", attrs=["dark"])
        elif self.category.isUnder(INCOME):
            amountText = colored(quantityArrow, "green")
        else:
            amountText = colored(quantityArrow, "white")
        relatedAcc = self.relatedTo if self.relatedTo != None else ""
        categoryLabel = "" if self.category == None else self.category.label
        return f"<Transaction: {categoryLabel:20s} {self.date} " + \
               f"{self.account:>20s} {amountText} {relatedAcc:25s} {self.description}>"

def syntheticTransaction(
    date: Date,
    description: str,
    amount: MoneyAmount,
    category: Category,
    account: Account,
    rawRecord: str = "",
    sourceLocation: Optional[Tuple[str, int]] = None,
    relatedTo: Optional[Account] = None,
    isUnrealized: bool = False,
    isForecast: bool = False,
    referencedExchangeRates: ExchangeRates = EMPTY_EXCHANGE_RATES,
    amountIsRaw: bool = False
) -> Transaction:
    # if sourceLocation is None:
    #     callerFrame = mapOptional(currentframe(), lambda f: f.f_back)
    #     sourceLocation = makeSourceLocation(callerFrame)
    if category == INTERNAL_TRANSFER: assert(amountIsRaw)
    rawAmount = amount if amountIsRaw else MoneyAmount(amount.currency, 0)
    adjustments = () if amountIsRaw else (amount.quantity,)
    return Transaction(
        date=date,
        description=description,
        rawAmount=rawAmount,
        category=category,
        account=account,
        rawRecord=rawRecord,
        sourceLocation=sourceLocation,
        adjustments=adjustments,
        relatedTo=relatedTo,
        isUnrealized=isUnrealized,
        isForecast=isForecast,
        referencedExchangeRates=referencedExchangeRates)

def simpleCSVForTransaction(t: Transaction) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        t.date,
        t.account,
        t.description,
        t.adjustedAmount.quantity,
        t.adjustedAmount.currency
    ])
    return output.getvalue().strip()

def sumSingleCurrencyAdjustedAmounts(transactions: Iterable[Transaction]) -> MoneyAmount:
    return sumSingleCurrencyAmounts(t.adjustedAmount for t in transactions)

def printTransactionsAsCSV(ts: Iterable[Transaction]):
    print("\n".join(simpleCSVForTransaction(t) for t in ts))

def splitTransactions(
    transactions: List[Transaction],
    separatorCondition: Callable[[Transaction], bool]
) -> Tuple[List[List[Transaction]], Optional[List[Transaction]]]:
    results = []
    group = []
    leading = None
    # If there are consecutive transactions that meet
    # the condition, only separate once with the first
    # transaction.
    prevMeetsCond = False
    for trans in transactions:
        meetsCond = separatorCondition(trans)
        if meetsCond and not prevMeetsCond:
            if len(group) > 0 and leading == None:
                leading = group
            else: results.append(group)
            group = []
        group.append(trans)
        prevMeetsCond = meetsCond
    if len(group) > 0: results.append(group)
    return (results, leading)

def sourceLocationFromFrame(
    frame: Optional[FrameType],
    useNegativeLineNumWithTotalNumLines: Optional[int] = None
) -> Optional[Tuple[str, int]]:
    if frame is None: return None
    frameinfo = getframeinfo(frame)
    relativePath = os.path.relpath(frameinfo.filename, os.getcwd())
    lineNum = frameinfo.lineno
    if (totalNumLines := useNegativeLineNumWithTotalNumLines) is not None:
        lineNum = lineNum - totalNumLines
    return (relativePath, lineNum)

def makeSourceLocation(frame: Optional[FrameType] = None):
    if frame is None:
        callerFrame = mapOptional(currentframe(), lambda f: f.f_back)
        frame = callerFrame
    return sourceLocationFromFrame(frame)

def makeManualTransactionFn(
    currentFilePath: str,
    useNegativeLineNum: bool,
    account: Account,
    currency: Currency
):
    totalNumLines = None
    if useNegativeLineNum:
        with open(currentFilePath, "r") as f:
            totalNumLines = sum(1 for _ in f.readlines())
    def makeTransaction(
        year: int,
        month: int,
        day: int,
        description: str,
        quantity: float
    ) -> Transaction:
        callerFrame = mapOptional(currentframe(), lambda f: f.f_back)
        return Transaction(
            sourceLocation=sourceLocationFromFrame(
                callerFrame, useNegativeLineNumWithTotalNumLines=totalNumLines),
            account=account,
            rawAmount=MoneyAmount(currency, quantity),
            category=INCOME if quantity > 0 else EXPENSE,
            date=Date(year=year, month=month, day=day),
            description=description,
            rawRecord="")
    return makeTransaction

def isMainSalaryIncome(trans: Transaction):
    return (trans.category == SALARY and
            trans.adjustedAmount.currency == JPY and
            trans.adjustedAmount.quantity > 200000)

def sortedByDate(transactions: List[Transaction]) -> List[Transaction]:
    return sorted(transactions, key=lambda t: t.date)

def splitIntoTimeSectionsBySalaryIncome(
    transactions: List[Transaction]
) -> Tuple[List[List[Transaction]], Optional[List[Transaction]]]:
    return splitTransactions(sortedByDate(transactions), isMainSalaryIncome)

def minMaxDateOf(transactions):
    dates = [t.date for t in transactions]
    return (min(dates), max(dates))

def earnedIncomesOf(trans):
    return [t for t in trans if t.category.isUnder(EARNED_INCOME)]

def expensesOf(trans):
    return [t for t in trans if t.category.isUnder(EXPENSE)]

def memo(wrappedFn):
    cache = {}
    def memoizedFn(*args):
        if args not in cache:
            cache[args] = wrappedFn(*args)
        return cache[args]
    return memoizedFn

# [[a]] -> [a]
T = TypeVar("T")
def concat(groups: List[List[T]]) -> List[T]:
    flatten = []
    for g in groups: flatten.extend(g)
    return flatten

HashableU = TypeVar("HashableU", bound=Hashable)
def groupAsDict(
    items: Iterator[T], keyFn: Callable[[T], HashableU]
) -> Dict[HashableU, List[T]]:
    d: Dict[HashableU, List[T]] = {}
    for item in items:
        key = keyFn(item)
        l = d.get(key, [])
        l.append(item)
        d[key] = l
    return d

def popFirstMatch(items: List[T], matching: Callable[[T], bool]) -> Optional[T]:
    for idx, item in enumerate(items):
        if not matching(item): continue
        return items.pop(idx)
    return None

U = TypeVar("U")
def mapOptional(optional: Optional[T], transform: Callable[[T], U]) -> Optional[U]:
    if optional is None: return None
    return transform(optional)
