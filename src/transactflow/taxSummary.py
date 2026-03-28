from os import read
from transactflow.base import *
from dataclasses import dataclass, field
from transactflow.multiCurrency import totalAdjustedAmountAsJPY
from transactflow.taxCalculation.nationalTaxCalculation import NationalTaxCalculator, DependentsConfig
from transactflow.processes.runAll import run
import transactflow.taxCalculation.localTaxCalculation as localTaxCalculation

@dataclass()
class TaxEstimationInfo:
    paidSalaryFraction: float
    vestedEquityFraction: float

@dataclass()
class AmountsByTaxType:
    forNationalTax: float
    forLocalTax: float
    @property
    def total(self): return self.forNationalTax + self.forLocalTax

@dataclass()
class EstimatedTaxSavings:
    """
    Estimated national and tax savings from e.g. furusato donations.

    Savings are estimated by calculating difference between tax amounts with and without the
    relevant saving method. Since the order of evaluation can affect the value distribution,
    estimation should start with none of the saving methods applied (to get the maximum tax amount),
    then gradually applying each method, in the same order as corrsponding properties are defined,
    to obtain the saving amount for each.
    """
    amountForFurusato: AmountsByTaxType
    amountForGeneralDependents: List[AmountsByTaxType]
    amountForSpecificDependents: List[AmountsByTaxType]
    amountForElderlyDependentLivingTogether: List[AmountsByTaxType]
    amountForElderlyDependentOthers: List[AmountsByTaxType]
    amountForHousingBenefit: AmountsByTaxType

    @property
    def totalAmount(self) -> float:
        return sum(ams.total for ams in [
            self.amountForFurusato
        ] +
            self.amountForGeneralDependents +
            self.amountForSpecificDependents +
            self.amountForElderlyDependentLivingTogether +
            self.amountForElderlyDependentOthers +
        [
            self.amountForHousingBenefit
        ])

@dataclass()
class TaxSummary:
    year: int
    currency: Currency
    salary: float = 0
    bonus: float = 0
    equity: float = 0
    housingBenefitNonTaxable: float = 0
    capitalGain: float = 0
    salarySocialSecurity: float = 0
    bonusSocialSecurity: float = 0
    salaryWithholding: float = 0
    bonusWithholding: float = 0
    medicalFee: float = 0
    nationalTaxPrepayment: float = 0
    dependentsConfig: DependentsConfig = field(default_factory=DependentsConfig)
    furusatoTotal: float = 0
    estimationInfo: Optional[TaxEstimationInfo] = None

    @property
    def withholdingTotal(self) -> float:
        return self.salaryWithholding + self.bonusWithholding
    
    @property
    def socialSecurityTotal(self) -> float:
        return self.salarySocialSecurity + self.bonusSocialSecurity

    @property
    def totalCompensation(self) -> float:
        return self.salary + self.bonus + self.equity

    @property
    def nationalTaxToBePaid(self) -> float:
        """
        National tax to pay in the following year (withholding not included).
        Given how tax withholding and year end adjustment works, this should be
        entirely caused by equity (and other non-salary/bonus) income.
        """
        return NationalTaxCalculator(
            forYear=self.year,
            totalCompensation=self.totalCompensation,
            withholding=self.withholdingTotal,
            capitalGain=self.capitalGain,
            socialSecurity=self.socialSecurityTotal,
            medicalFee=self.medicalFee,
            lifeInsurance=0.0,
            earthquakeInsurace=0.0,
            dependentsConfig=self.dependentsConfig,
            furusato=self.furusatoTotal,
            prepayment=self.nationalTaxPrepayment).nationalTaxToPay

    @property
    def totalLocalTax(self) -> float:
        return localTaxCalculation.LocalTaxCalculator(
            forYear=self.year,
            totalCompensation=self.totalCompensation,
            capitalGain=self.capitalGain,
            socialSecurity=self.socialSecurityTotal,
            medicalFee=self.medicalFee,
            lifeInsurance=0.0,
            earthquakeInsurace=0.0,
            dependentsConfig=self.dependentsConfig,
            furusato=self.furusatoTotal).shibuyaLocalTax

    @property
    def segmentedTotalLocalTax(self) -> SegmentedTotals:
        totalIfOnlySalary = localTaxCalculation.LocalTaxCalculator(
            forYear=self.year,
            totalCompensation=self.salary,
            capitalGain=self.capitalGain,
            socialSecurity=self.salarySocialSecurity,
            medicalFee=self.medicalFee,
            lifeInsurance=0.0,
            earthquakeInsurace=0.0,
            dependentsConfig=self.dependentsConfig,
            furusato=self.furusatoTotal).shibuyaLocalTax
        totalIfSalaryBonus = localTaxCalculation.LocalTaxCalculator(
            forYear=self.year,
            totalCompensation=self.salary + self.bonus,
            capitalGain=self.capitalGain,
            socialSecurity=self.salarySocialSecurity + self.bonusSocialSecurity,
            medicalFee=self.medicalFee,
            lifeInsurance=0.0,
            earthquakeInsurace=0.0,
            dependentsConfig=self.dependentsConfig,
            furusato=self.furusatoTotal).shibuyaLocalTax
        totalIfEverything = self.totalLocalTax
        assert(totalIfOnlySalary <= totalIfSalaryBonus <= totalIfEverything)
        return SegmentedTotals(currency=self.currency,
                               forSalary=totalIfOnlySalary,
                               forBonus=totalIfSalaryBonus - totalIfOnlySalary,
                               forEquity=totalIfEverything - totalIfSalaryBonus,
                               forAll=totalIfEverything)

    @property
    def estimatedTaxSavings(self) -> EstimatedTaxSavings:
        def separateSaving(
            before: TaxSummary,
            removeSaving: Callable[[TaxSummary], TaxSummary]
        ) -> Tuple[TaxSummary, AmountsByTaxType]:
            import rich
            # print("before:")
            # rich.print(before)
            after = removeSaving(before)
            # print("after:")
            # rich.print(after)
            # input("continue?")
            savingAmounts = AmountsByTaxType(
                forNationalTax=after.nationalTaxToBePaid - before.nationalTaxToBePaid,
                forLocalTax=after.totalLocalTax - before.totalLocalTax)
            return after, savingAmounts
        summary = replace(self)
        summary, furusatoSavings = separateSaving(summary, lambda s: replace(s, furusatoTotal=0))
        def evaluateDependentsSaving(
            before: TaxSummary,
            getNumDependents: Callable[[TaxSummary], int],
            applyNumDependents: Callable[[TaxSummary, int], TaxSummary],
        ) -> Tuple[TaxSummary, List[AmountsByTaxType]]:
            amountsItems = []
            summary = before
            while (numDependents := getNumDependents(summary)) > 0:
                summary, savingAmounts = separateSaving(
                    summary, lambda s: applyNumDependents(s, numDependents - 1)
                )
                amountsItems.append(savingAmounts)
            return (summary, amountsItems)
        summary, generalDependentAmountsItems = evaluateDependentsSaving(
            summary,
            getNumDependents=lambda s: s.dependentsConfig.numGeneralDependents,
            applyNumDependents=lambda s, num: replace(
                s, dependentsConfig=replace(s.dependentsConfig, numGeneralDependents=num)
            ))
        summary, specificDependentAmountsItems = evaluateDependentsSaving(
            summary,
            getNumDependents=lambda s: s.dependentsConfig.numSpecificDependents,
            applyNumDependents=lambda s, num: replace(
                s, dependentsConfig=replace(s.dependentsConfig, numSpecificDependents=num)
            ))
        summary, elderlyDependentLivingTogetherDependentAmountsItems = evaluateDependentsSaving(
            summary,
            getNumDependents=lambda s: s.dependentsConfig.numElderlyDependentLivingTogether,
            applyNumDependents=lambda s, num: replace(
                s, dependentsConfig=replace(
                    s.dependentsConfig, numElderlyDependentLivingTogether=num
                )
            ))
        summary, elderlyDependentOthersAmountsItems = evaluateDependentsSaving(
            summary,
            getNumDependents=lambda s: s.dependentsConfig.numElderlyDependentOthers,
            applyNumDependents=lambda s, num: replace(
                s, dependentsConfig=replace(s.dependentsConfig, numElderlyDependentOthers=num)
            ))
        summary, housingBenefitSavings = separateSaving(
            summary,
            lambda s: replace(s, housingBenefitNonTaxable=0, salary=s.salary + s.housingBenefitNonTaxable)
        )
        return EstimatedTaxSavings(
            amountForFurusato=furusatoSavings,
            amountForGeneralDependents=generalDependentAmountsItems,
            amountForSpecificDependents=specificDependentAmountsItems,
            amountForElderlyDependentLivingTogether=elderlyDependentLivingTogetherDependentAmountsItems,
            amountForElderlyDependentOthers=elderlyDependentOthersAmountsItems,
            amountForHousingBenefit=housingBenefitSavings
        )


    def estimateMaximumFurusato(self) -> Tuple[int, Dict[int, AmountsByTaxType]]:
        """
        Returns the estimated maximum amount of effective furusato donations, exceeding which
        results in no further tax benefit.
        """
        # TODO: Investigate and fix the inaccurate estimations. It seems like tax deduction
        # calculations take an unreasonably large amount (much larger than website estimations.)
        # Clear the prepayment amount, otherwise calculation may report error due to the prepayment
        # amount exceeding total payment amount.
        baseSummary = replace(self, nationalTaxPrepayment=0)
        # Binary search between 0 and `salary + bonus + equity`
        def binarySearch(low: int, delta: int, loggedAttempts: Dict[int, AmountsByTaxType]) -> int:
            if delta <= 0: return low
            mid = low + int(delta / 2)
            high = low + delta
            def savingsFor(furusatoTotal: float):
                return replace(
                    baseSummary, furusatoTotal=furusatoTotal
                ).estimatedTaxSavings.amountForFurusato
            loggedAttempts[low] = (lowSavings := savingsFor(float(low)))
            loggedAttempts[mid] = (midSavings := savingsFor(float(mid)))
            loggedAttempts[high] = (highSavings := savingsFor(float(high)))
            if (
                midSavings.forNationalTax < highSavings.forNationalTax and
                midSavings.forLocalTax < highSavings.forLocalTax
            ):
                return binarySearch(mid, high - mid, loggedAttempts)
            elif (
                lowSavings.forNationalTax < midSavings.forNationalTax and
                lowSavings.forLocalTax < midSavings.forLocalTax
            ):
                return binarySearch(low, mid - low, loggedAttempts)
            else: return low
        loggedAttempts: Dict[int, AmountsByTaxType] = {}
        estimatedMaximum = binarySearch(
            low=0, delta=int(self.salary + self.bonus + self.equity), loggedAttempts=loggedAttempts)
        return estimatedMaximum, loggedAttempts


def yearlyTaxSummaryFromTransactions(year: int,
                                     estimateFullYear: bool,
                                     transactions: List[Transaction],
                                     bonusOverride: Optional[float] = None,
                                     equityOverride: Optional[float] = None) -> TaxSummary:
    """
    Tax summary for the given year, generated from a list of transactions, assuming the it contains
    all payslip income (after annotation is applied) and equity transactions known so far.

    If `estimateFullYear` is `True`, it tries to give estimated values as if all income for the full
    year are already realized, following this way of guessing:
        Salary: assume amount each missing month = avg(amount each existing month)
        Bonus: assume missing month has no bonus amount (usually the case, biggest bonus is on Jan)
        Equity: take unvested units into account, using the rates today
    """
    accumulatingSummary = TaxSummary(year=year, currency=JPY)
    transactionsInYear = [ t for t in transactions if t.date.year == year ]
    def totalOfExactCategory(cat: Category, useForecast: bool = False, check: bool = True) -> float:
        quantity = abs(
            totalAdjustedAmountAsJPY(
                t for t in transactionsInYear
                if t.category == cat and t.isForecast == useForecast)
        )
        if useForecast and check: assert(quantity > 0)
        return quantity
    def addSalaryItems(useForecast: bool):
        def totalOf(cat: Category): return totalOfExactCategory(cat, useForecast=useForecast)
        # This amount does not include NON_TAXABLE_SALARY.
        accumulatingSummary.salary += totalOf(SALARY)
        accumulatingSummary.salaryWithholding += totalOf(NATIONAL_TAX_WITHHOLDING_SALARY)
        accumulatingSummary.salarySocialSecurity += totalOf(HELATH_INSURANCE_SALARY)
        accumulatingSummary.salarySocialSecurity += totalOf(WELFARE_SALARY)
        accumulatingSummary.salarySocialSecurity += totalOf(UNEMPL_INS_SALARY)
    addSalaryItems(useForecast=False)
    def addBonusItems(useForecast: bool):
        def totalOf(cat: Category): return totalOfExactCategory(cat, useForecast=useForecast)
        accumulatingSummary.bonus += totalOf(BONUS)
        accumulatingSummary.bonusWithholding += totalOf(NATIONAL_TAX_WITHHOLDING_BONUS)
        accumulatingSummary.bonusSocialSecurity += totalOf(HELATH_INSURANCE_BONUS)
        accumulatingSummary.bonusSocialSecurity += totalOf(WELFARE_BONUS)
        accumulatingSummary.bonusSocialSecurity += totalOf(UNEMPL_INS_BONUS)
    addBonusItems(useForecast=False)
    accumulatingSummary.equity += totalOfExactCategory(EQUITY_VESTING, useForecast=False)
    accumulatingSummary.housingBenefitNonTaxable += totalOfExactCategory(
        NON_TAXABLE_SALARY_HOUSING_BENEFIT, useForecast=False)
    accumulatingSummary.capitalGain += totalOfExactCategory(CAPITAL_GAIN, useForecast=False)
    accumulatingSummary.nationalTaxPrepayment += totalOfExactCategory(
        NATIONAL_TAX_PREPAYMENT, useForecast=False)
    accumulatingSummary.furusatoTotal += totalOfExactCategory(FURUSATO_DONATION, useForecast=False)
    hasAnyForecast = any(t for t in transactionsInYear if t.isForecast)
    if estimateFullYear:
        if hasAnyForecast:
            copyBeforeEstimation = replace(accumulatingSummary)
            addSalaryItems(useForecast=True)
            accumulatingSummary.equity += totalOfExactCategory(
                EQUITY_VESTING, useForecast=True, check=False)
            accumulatingSummary.housingBenefitNonTaxable += totalOfExactCategory(
                NON_TAXABLE_SALARY_HOUSING_BENEFIT, useForecast=True)
            paidSalaryFraction = copyBeforeEstimation.salary / accumulatingSummary.salary
            vestedEquityFraction = copyBeforeEstimation.equity / accumulatingSummary.equity
            accumulatingSummary.estimationInfo = TaxEstimationInfo(
                paidSalaryFraction=paidSalaryFraction,
                vestedEquityFraction=vestedEquityFraction)
        else:
            accumulatingSummary.estimationInfo = TaxEstimationInfo(
                paidSalaryFraction=1.0,
                vestedEquityFraction=1.0
            )
    if bonusOverride: accumulatingSummary.bonus = bonusOverride
    if equityOverride: accumulatingSummary.equity = equityOverride
    return accumulatingSummary

def printTaxSummary(summary: TaxSummary):
    import rich
    nationalTaxToBePaid = summary.nationalTaxToBePaid
    totalNationalTax = summary.nationalTaxToBePaid + summary.nationalTaxPrepayment
    segmentedTotalLocalTax = summary.segmentedTotalLocalTax
    netTotalTax = summary.nationalTaxToBePaid + summary.segmentedTotalLocalTax.forAll
    salaryBonusSegments: List[Tuple[str, float, float]] = [
        ("Income", summary.salary, summary.bonus),
        ("Social security", summary.salarySocialSecurity, summary.bonusSocialSecurity),
        ("Withholding", summary.salaryWithholding, summary.bonusWithholding)
    ]
    rich.print(summary)
    rich.print(f"Total compensation: {summary.totalCompensation}")
    rich.print(f"Total income: {summary.salary + summary.bonus + summary.equity}")
    for name, salaryAmount, bonusAmount in salaryBonusSegments:
        rich.print(f"(Salary + Bonus) {name}: {salaryAmount + bonusAmount}")
    rich.print(f"Remaining national tax to pay: {nationalTaxToBePaid}")
    rich.print(f"Total national tax: {totalNationalTax}")
    rich.print(f"Local tax in segments: {segmentedTotalLocalTax}")
    rich.print(f"National tax to pay + local tax total: {netTotalTax}")
    rich.print("Estimated savings:")
    savings = summary.estimatedTaxSavings
    rich.print(savings)
    rich.print(f"Total saving: {savings.totalAmount}")
    estimatedMaximumFurusato, furusatoSavingEstimations = summary.estimateMaximumFurusato()
    sortedFurusatoEstimations = [
        (furu, furusatoSavingEstimations[furu]) for furu in sorted(furusatoSavingEstimations.keys())
    ]
    rich.print(f"Estimated max furusato: {estimatedMaximumFurusato}")
    rich.print("Max furusato estimations (savings for donation amount):")
    rich.print(sortedFurusatoEstimations)


def printYearlyTaxSummary(
    year: int,
    customizeSummary: Optional[Callable[[TaxSummary], None]] = None,
    bonusOverride: Optional[float] = None,
    equityOverride: Optional[float] = None
):
    transactions = run(includeTaxProcesses=False)
    summary = yearlyTaxSummaryFromTransactions(
        year=year,
        estimateFullYear=True,
        transactions=transactions,
        bonusOverride=bonusOverride,
        equityOverride=equityOverride)
    if customizeSummary: customizeSummary(summary)
    print(f"Pre tax income total: {summary.salary + summary.bonus + summary.equity}")
    printTaxSummary(summary)
