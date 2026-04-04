from asyncio import threads
from typing import List
from ..taxSummary import AmountsByTaxType, yearlyTaxSummaryFromTransactions
from ..process import GroupedProcess, LazyGroupedProcess, Process, TaxRedistributionConfig, addTaxAdjustments, collectAndDistributeTax, funcProcess, funcProcessWrapper, matching, satisfyAny
from ..userConfig import forceReadUserConfig
from ..base import *

"""
Tax related processes to apply after loading all transactions.

Tax it is complicated and the items often should be moved
for clearer representation.

Tax items can span multiple years, here is an example of all tax items in 2020.

[Tax transactions happening on 2020]
- For 2018:
    - Local tax: salary deductions from first half 2020
- For 2019:
    - National tax: payment after Kakutei Shinkoku
    - Local tax: salary deductions from second half 2020
- For 2020:
    - National tax: withholding from salary and year end adjustments

[Tax on 2020 that will be paid in following years]
- Paid in 2021:
    - National tax: payment after Kakutei Shinkoku
    - Local tax: salary deductions from second half 2021
- Paid in 2022:
    - Local tax: salary deductions from first half 2022

That is, national tax span for 3 years, local tax span for 5 years(!)

Here is what to do for each type of tax item:

- National tax widthholding, and year end adjustment
    - Leave unchanged, or reproject to the same year (if YEA high)
- National tax payment after Kakutei Shinkoku
    - Reproject to (year - 1)
    - Forecast from (year + 1)
- Local tax deductions, first half year
    - Reproject to (year - 1)
    - Forecast from (year + 2)
- Local tax deductions, second half year
    - Reproject to (year - 2)
    - Forecast from (year + 1)
"""

def reprojectUnpaidNationalTax(toYear: int, unpaidAmount: MoneyAmount) -> Process:
    assert(unpaidAmount.quantity >= 0)
    @funcProcess(customLabel=f"Reproject unpaid national tax to year {toYear}")
    def reprojectProcess(transactions: List[Transaction]) -> List[Transaction]:
        # Assume that all unpaid national tax is for equity. This will eventually be (almost)
        # correct, since the total of national tax withholding + year end adjustment will be
        # nearly the same as "national tax amount for salary + bonus". Ignore the unvested part
        # because only vested equity is taxable.
        return addTaxAdjustments(transactions,
                                 totalAbsAmount=unpaidAmount,
                                 toYear=toYear,
                                 weightUsingExactIncomeCat=EQUITY_VESTING,
                                 taxDescription="National tax yet to be paid (for vested equity)",
                                 taxCategory=ESTIMATED_UNPAID_TAX_EQUITY,
                                 taxAccount=PSEUDO_ACCOUNT)
    return reprojectProcess

def reprojectEstimatedTaxToBeCharged(toYear: int) -> Process:
    def redistributeNationalTaxPrepayment(verifyTotalTaxAmount: MoneyAmount):
        def prepaymentAmountIn(t: Transaction) -> float:
            isPrepayment = matching(year=toYear, exactCategory=NATIONAL_TAX_PREPAYMENT)
            return abs(t.adjustedAmount.quantity) if isPrepayment(t) else 0
        # TODO: Redistribution should not focus on vested equity. Update to
        # also redistribute to future months with unvested equity.
        return collectAndDistributeTax(
            toYear=toYear,
            label=f"Reproject national tax prepayment for {toYear} income",
            configForWeightingCategory={
                EQUITY_VESTING: TaxRedistributionConfig(
                    taxDescription="National tax prepayment reprojected",
                    taxCategory=NATIONAL_TAX_REPROJECTED_EQUITY,
                    getChargedTaxAbsAmount=prepaymentAmountIn,
                    verifyTotalTaxAmount=verifyTotalTaxAmount
                )
            },
        )

    @funcProcess(f"Reprojecting tax for {toYear} to be charged later")
    def func(transactions: List[Transaction]) -> List[Transaction]:
        taxSummary = yearlyTaxSummaryFromTransactions(toYear,
                                                      estimateFullYear=True,
                                                      transactions=transactions)
        # if toYear == 2025:
        #     print("============DEBUG===========")
        #     import rich
        #     rich.print(taxSummary)
        #     breakpoint()
        assert(taxSummary.estimationInfo is not None)
        assert(taxSummary.nationalTaxToBePaid > 0)
        print(f"Rough estimation of tax for {toYear}:\n" +
              f"Tax summary generated from transactions: {taxSummary}\n" +
              f"{taxSummary.nationalTaxToBePaid=} {taxSummary.segmentedTotalLocalTax=}")
        def asAmount(quantity: float): return MoneyAmount(taxSummary.currency, quantity)
        transactions = redistributeNationalTaxPrepayment(
            verifyTotalTaxAmount=asAmount(taxSummary.nationalTaxPrepayment))(transactions)
        # Assume that all unpaid national tax is for equity. This will eventually be (almost)
        # correct, since the total of national tax withholding + year end adjustment will be
        # nearly the same as "national tax amount for salary + bonus".
        transactions = reprojectUnpaidNationalTax(
            toYear=toYear, unpaidAmount=asAmount(taxSummary.nationalTaxToBePaid))(transactions)
        segmentedLocalTax = taxSummary.segmentedTotalLocalTax
        transactions = addTaxAdjustments(transactions,
                                         totalAbsAmount=asAmount(segmentedLocalTax.forSalary),
                                         toYear=toYear,
                                         weightUsingExactIncomeCat=SALARY,
                                         taxDescription="unpaid local tax (for salary)",
                                         taxCategory=ESTIMATED_UNPAID_TAX_SALARY,
                                         taxAccount=PSEUDO_ACCOUNT)
        transactions = addTaxAdjustments(transactions,
                                         totalAbsAmount=asAmount(segmentedLocalTax.forBonus),
                                         toYear=toYear,
                                         weightUsingExactIncomeCat=BONUS,
                                         taxDescription="unpaid local tax (for bonus)",
                                         taxCategory=ESTIMATED_UNPAID_TAX_BONUS,
                                         taxAccount=PSEUDO_ACCOUNT)
        transactions = addTaxAdjustments(transactions,
                                         totalAbsAmount=asAmount(segmentedLocalTax.forEquity),
                                         toYear=toYear,
                                         weightUsingExactIncomeCat=EQUITY_VESTING,
                                         taxDescription="unpaid local tax (for equity)",
                                         taxCategory=ESTIMATED_UNPAID_TAX_EQUITY,
                                         taxAccount=PSEUDO_ACCOUNT)
        return transactions
    return func

# TODO: Extend to partially replace `reprojectEstimatedTaxToBeCharged` for local tax estimation
# of an incomplete year. This is essentially the case when `determinedTotals` is None.
# In such case, `yearlyTaxSummaryFromTransactions` can be helpful (with estimateFullYear=True).
def reprojectLocalTaxWithSegmentation(toYear: int,
                                      amountCharged: Callable[[Transaction], float],
                                      determinedTotals: SegmentedTotals) -> Process:
    """
    All in one solution for local tax reprojection.
    Reproject paid local tax to toYear as synthetic transactions, where the paid amounts are
    defined by `amountCharged`.
    If the total amount changed is less than `determinedTotals`, then the difference is used to
    reproject unpaid local tax.
    The ratio of salary/bonus/equity from `deteminedTotals` is used to split the reprojection
    into the same 3 parts.
    """
    @funcProcess(f"Reproject local tax with segmentation to {toYear}")
    def func(transactions: List[Transaction]) -> List[Transaction]:
        amountChargedSalary = lambda t: amountCharged(t) * determinedTotals.salaryOfAllRatio
        amountChargedBonus = lambda t: amountCharged(t) * determinedTotals.bonusOfAllRatio
        amountChargedEquity = lambda t: amountCharged(t) * determinedTotals.equityOfAllRatio
        def reprojectCharged() -> Process:
            redistributionConfigForSalary = TaxRedistributionConfig(
                taxDescription=f"local tax charged for year {toYear} (salary)",
                taxCategory=LOCAL_TAX_REPROJECTED_SALARY,
                getChargedTaxAbsAmount=amountChargedSalary,
            )
            redistributionConfigForBonus = TaxRedistributionConfig(
                taxDescription=f"local tax charged for year {toYear} (bonus)",
                taxCategory=LOCAL_TAX_REPROJECTED_BONUS,
                getChargedTaxAbsAmount=amountChargedBonus,
            )
            redistributionConfigForEquity = TaxRedistributionConfig(
                taxDescription=f"local tax charged for year {toYear} (equity)",
                taxCategory=LOCAL_TAX_REPROJECTED_EQUITY,
                getChargedTaxAbsAmount=amountChargedEquity,
            )
            return collectAndDistributeTax(
                toYear=toYear,
                label=f"Reproject local tax charged for {toYear} income",
                configForWeightingCategory={
                    SALARY: redistributionConfigForSalary,
                    BONUS: redistributionConfigForBonus,
                    EQUITY_VESTING: redistributionConfigForEquity,
                }
            )
        def reprojectUnpaid() -> List[Process]:
            unpaidTotal = determinedTotals.forAll - sum(amountCharged(t) for t in transactions)
            # If total charged amount is more than the total amount given as the argument,
            # something must be wrong.
            if unpaidTotal < -100: assert(False)
            if unpaidTotal <= 0: return []
            unpaidAmountSalary = determinedTotals.forSalary - sum(amountChargedSalary(t) for t in transactions)
            unpaidAmountBonus = determinedTotals.forBonus - sum(amountChargedBonus(t) for t in transactions)
            unpaidAmountEquity = determinedTotals.forEquity - sum(amountChargedEquity(t) for t in transactions)
            assert(unpaidAmountSalary >= 0)
            assert(unpaidAmountBonus >= 0)
            assert(unpaidAmountEquity >= 0)
            def asAmount(quantity: float): return MoneyAmount(determinedTotals.currency, quantity)
            @funcProcess()
            def addUnpaidAmountsForSalary(transactions: List[Transaction]) -> List[Transaction]:
                return addTaxAdjustments(transactions,
                                         totalAbsAmount=asAmount(unpaidAmountSalary),
                                         toYear=toYear,
                                         weightUsingExactIncomeCat=SALARY,
                                         taxDescription=f"Local tax yet to be charged for {toYear} (for salary)",
                                         taxCategory=ESTIMATED_UNPAID_TAX_SALARY,
                                         taxAccount=PSEUDO_ACCOUNT)
            @funcProcess()
            def addUnpaidAmountsForBonus(transactions: List[Transaction]) -> List[Transaction]:
                return addTaxAdjustments(transactions,
                                         totalAbsAmount=asAmount(unpaidAmountBonus),
                                         toYear=toYear,
                                         weightUsingExactIncomeCat=BONUS,
                                         taxDescription=f"Local tax yet to be charged for {toYear} (for bonus)",
                                         taxCategory=ESTIMATED_UNPAID_TAX_BONUS,
                                         taxAccount=PSEUDO_ACCOUNT)
            @funcProcess()
            def addUnpaidAmountsForEquity(transactions: List[Transaction]) -> List[Transaction]:
                return addTaxAdjustments(transactions,
                                         totalAbsAmount=asAmount(unpaidAmountEquity),
                                         toYear=toYear,
                                         weightUsingExactIncomeCat=EQUITY_VESTING,
                                         taxDescription=f"Local tax yet to be charged for {toYear} (for equity)",
                                         taxCategory=ESTIMATED_UNPAID_TAX_EQUITY,
                                         taxAccount=PSEUDO_ACCOUNT)
            return [
                addUnpaidAmountsForSalary,
                addUnpaidAmountsForBonus,
                addUnpaidAmountsForEquity
            ]
        return GroupedProcess(label=None,
                              atomic=True,
                              processes=[reprojectCharged()] + reprojectUnpaid())(transactions)
    return func

def chargedFurusatoDonationInYear(year: int) -> Callable[[Transaction], float]:
    def amountInTransaction(t: Transaction) -> float:
        if t.date.year != year: return 0
        if not t.category.isUnder(FURUSATO_DONATION): return 0
        return abs(t.adjustedAmount.quantity)
    return amountInTransaction

def dateIsWithinLocalTaxSalaryDeduction(date: Date, yearOfIncome: int) -> bool:
    return (
        (date.year == (yearOfIncome + 1) and date.month >= 6) or
        (date.year == (yearOfIncome + 2) and date.month <= 5)
    )

def amountIfLocalTaxSalaryDeduction(transaction: Transaction, yearOfIncome: int) -> float:
    if "Synthetic transaction: local tax deduction" not in transaction.description: return 0
    if dateIsWithinLocalTaxSalaryDeduction(transaction.date, yearOfIncome):
        return abs(transaction.adjustedAmount.quantity)
    return 0

def processesReprojectingTaxFinalized(
        yearOfIncome: int,
        finalizedlocalTaxTotals: SegmentedTotals,
        finalizedEquityNationalTaxAmount: MoneyAmount,
        chargedLocalTaxAbsAmountIn: Callable[[Transaction], float],
        chargedNationalTaxAbsAmountIn: Callable[[Transaction], float],
        savedTaxFromDependentTransferAbsAmountIn: Callable[[Transaction], float],
        savedTaxFromRentAbsAmountIn: Callable[[Transaction], float]):
    @funcProcess()
    def pruneForecastedLocalTaxDeductions(transactions: List[Transaction]) -> List[Transaction]:
        # The reprojection process generates unpaid local tax transactions, which would overlap with
        # forecasted local tax deductions, therefore remove the forecasted versions which are likely
        # less accurate.
        return [
            t for t in transactions
            if not (
                t.isForecast and
                t.category.isUnder(LOCAL_TAX_DEDUCTION) and
                dateIsWithinLocalTaxSalaryDeduction(t.date, yearOfIncome)
            )
        ]

    @funcProcessWrapper(customLabel=f"Reproject paid and unpaid local tax to {yearOfIncome} income")
    def reprojectPaidAndUnpaidLocalTax():
        return reprojectLocalTaxWithSegmentation(
            toYear=yearOfIncome,
            amountCharged=chargedLocalTaxAbsAmountIn,
            determinedTotals=finalizedlocalTaxTotals)

    reprojectPaidAndUnpaidNationalTax = collectAndDistributeTax(
        toYear=yearOfIncome,
        label=f"Reproject paid and unpaid national tax for {yearOfIncome} equity",
        configForWeightingCategory={
            EQUITY_VESTING: TaxRedistributionConfig(
                taxDescription=f"national tax for {yearOfIncome}, paid in {yearOfIncome + 1}",
                taxCategory=NATIONAL_TAX_REPROJECTED_EQUITY,
                getChargedTaxAbsAmount=chargedNationalTaxAbsAmountIn,
                runProcessWithTotalTaxAmount=lambda amount: reprojectUnpaidNationalTax(
                    toYear=yearOfIncome,
                    unpaidAmount=finalizedEquityNationalTaxAmount - amount,
                ),
            )
        },
    )

    reprojectFurusatoDonation = collectAndDistributeTax(
        toYear=yearOfIncome,
        label=f"Reproject furusato tax for {yearOfIncome} income",
        configForWeightingCategory={
            EQUITY_VESTING: TaxRedistributionConfig(
                taxDescription=f"Furusato tax for {yearOfIncome}",
                # TODO: split into reprojected national tax and local tax.
                taxCategory=SAVED_TAX_FROM_FURUSATO_DONATION,
                getChargedTaxAbsAmount=chargedFurusatoDonationInYear(yearOfIncome),
            )
        },
    )

    reprojectDependentTransferTaxSaving = collectAndDistributeTax(
        toYear=yearOfIncome,
        label=f"Reproject saved tax from depedent transfer for {yearOfIncome} income",
        configForWeightingCategory={
            EQUITY_VESTING: TaxRedistributionConfig(
                taxDescription=f"Tax saving from dependent transfer for {yearOfIncome}",
                # TODO: split into reprojected national tax and local tax.
                taxCategory=SAVED_TAX_FROM_DEPENDENT_TRANSFER,
                getChargedTaxAbsAmount=savedTaxFromDependentTransferAbsAmountIn,
            )
        },
    )

    reprojectRentTaxSaving = collectAndDistributeTax(
        toYear=yearOfIncome,
        label=f"Reproject saved tax from housingBenefit for {yearOfIncome} income",
        configForWeightingCategory={
            EQUITY_VESTING: TaxRedistributionConfig(
                taxDescription=f"Tax saving from rent for {yearOfIncome}",
                # TODO: split into reprojected national tax and local tax.
                taxCategory=SAVED_TAX_FROM_RENT,
                getChargedTaxAbsAmount=savedTaxFromRentAbsAmountIn,
            )
        },
    )

    return [
        pruneForecastedLocalTaxDeductions,
        reprojectPaidAndUnpaidLocalTax,
        reprojectPaidAndUnpaidNationalTax,
        reprojectFurusatoDonation,
        reprojectDependentTransferTaxSaving,
        reprojectRentTaxSaving
    ]


def _buildTaxProcesses() -> List[Process]:
    config = forceReadUserConfig().processes
    if config is None: return []
    userSupplied = config.taxProcess
    return [] if userSupplied is None else [userSupplied]


process = LazyGroupedProcess(label="Tax reprojection", buildProcesses=_buildTaxProcesses)
