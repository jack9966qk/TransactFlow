from typing import List
from ..base import *
from ..multiCurrency import MultiCurrencyAmount
from ..process import funcMatching, funcProcess, takeFirstMatch
from ..processes.payslipAnnotationItem import PayslipAnnotationItem
from ..userConfig import forceReadUserConfig

def expectedTotalBalanceDelta() -> MultiCurrencyAmount:
    annotations = forceReadUserConfig().processes.payslipAnnotations
    assert annotations is not None
    totalPensionVoluntaryQuantity = sum(item.pensionVoluntary for item in annotations)
    return MultiCurrencyAmount(quantities={JPY: totalPensionVoluntaryQuantity})

@funcProcess()
def applyPayslipAnnotations(transactions: List[Transaction]) -> List[Transaction]:
    """
    Read payslip annotation file and update the salary and bonus transactions with more details.
    Specifically:
        - For each payslip item, match a salary/bonus transaction and replace it
        - Verify that "payable" under each payslip item matches the corresponding transaction
          (each payslip item is internally consistent, verified upon init)
        - Add synthesized transactions for all gross income and its deduction items
    """
    annotations = forceReadUserConfig().processes.payslipAnnotations
    if annotations is None:
        return transactions
    allNewSynthesizedTransactions = []
    remaining = transactions
    for item in annotations:
        originalFormat = (
            f"PayslipAnnotationItem with date as {item.date}, type as {item.type}, " +
            " remaining omitted.")
        @funcMatching(f"Matching annotation: {item!r}")
        def matchingAnnotation(t: Transaction) -> bool:
            return (t.date == item.date and t.rawAmount == MoneyAmount(JPY, item.payable))
        matched, remaining = takeFirstMatch(remaining, matchingAnnotation)
        assert(matched is not None)
        year, month = item.date.year, item.date.month
        incomeCategory = BONUS if "bonus" in item.type.lower() else SALARY
        withholdingCat, welfareCat, healthInsCat, unemplInsCat, miscDeductionCat = (
            NATIONAL_TAX_WITHHOLDING_SALARY,
            WELFARE_SALARY,
            HELATH_INSURANCE_SALARY,
            UNEMPL_INS_SALARY,
            MISC_INCOME_DEDUCTION_SALARY) if incomeCategory == SALARY else (
            NATIONAL_TAX_WITHHOLDING_BONUS,
            WELFARE_BONUS,
            HELATH_INSURANCE_BONUS,
            UNEMPL_INS_BONUS,
            MISC_INCOME_DEDUCTION_BONUS)
        synthesizedForThisItem = [
            synthesizedTransaction(
                date=item.date,
                description=f"Payslip {incomeCategory.label} income {year}/{month}",
                amount=MoneyAmount(JPY, item.gross - item.yearEndAdj - item.reimbursement - item.pensionVoluntary),
                account=matched.account,
                originalFormat=originalFormat,
                sourceLocation=item.sourceLocation,
                category=incomeCategory,
                amountIsRaw=True),
            synthesizedTransaction(
                date=item.date,
                description=f"Synthesized transaction: health insurance deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.healthInsurance),
                account=matched.account,
                originalFormat=originalFormat,
                sourceLocation=item.sourceLocation,
                category=healthInsCat,
                amountIsRaw=True),
            synthesizedTransaction(
                date=item.date,
                description=f"Synthesized transaction: welfare deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.welfare),
                account=matched.account,
                originalFormat=originalFormat,
                sourceLocation=item.sourceLocation,
                category=welfareCat,
                amountIsRaw=True),
            synthesizedTransaction(
                date=item.date,
                description=f"Synthesized transaction: unempl. ins deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.unemplIns),
                account=matched.account,
                originalFormat=originalFormat,
                sourceLocation=item.sourceLocation,
                category=unemplInsCat,
                amountIsRaw=True),
            synthesizedTransaction(
                date=item.date,
                description=f"Synthesized transaction: misc income deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.miscDeduction),
                account=matched.account,
                originalFormat=originalFormat,
                sourceLocation=item.sourceLocation,
                category=miscDeductionCat,
                amountIsRaw=True),
            synthesizedTransaction(
                date=item.date,
                description=f"Synthesized transaction: national tax deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.nationalTax),
                account=matched.account,
                originalFormat=originalFormat,
                sourceLocation=item.sourceLocation,
                category=withholdingCat,
                amountIsRaw=True),
        ]

        if item.pensionVoluntary > 0:
            synthesizedForThisItem.append(
                synthesizedTransaction(
                    date=item.date,
                    description=f"Synthesized transaction: Pension voluntary contribution on {year}/{month}",
                    amount=MoneyAmount(JPY, item.pensionVoluntary),
                    account=PENSION,
                    originalFormat=originalFormat,
                    sourceLocation=item.sourceLocation,
                    category=PENSION_CONTRIBUTION,
                    relatedTo=EMPLOYER,
                    amountIsRaw=True)
            )

        if item.housingBenefitTaxable > 0:
            synthesizedForThisItem.append(
                synthesizedTransaction(
                    date=item.date,
                    description=f"Synthesized transaction: taxable portion of rent (housingBenefit) on {year}/{month}",
                    amount=MoneyAmount(JPY, -item.housingBenefitTaxable),
                    account=matched.account,
                    originalFormat=originalFormat,
                    sourceLocation=item.sourceLocation,
                    category=RENT,
                    amountIsRaw=True),
            )
        if item.housingBenefitNonTaxable > 0:
            synthesizedForThisItem.append(
                synthesizedTransaction(
                    date=item.date,
                    description=f"Synthesized transaction: non taxable salary for housingBenefit on {year}/{month}",
                    amount=MoneyAmount(JPY, item.housingBenefitNonTaxable),
                    account=matched.account,
                    originalFormat=originalFormat,
                    sourceLocation=item.sourceLocation,
                    category=NON_TAXABLE_SALARY_HOUSING_BENEFIT,
                    amountIsRaw=True)
            )
            synthesizedForThisItem.append(
                synthesizedTransaction(
                    date=item.date,
                    description=f"Synthesized transaction: non-taxable portion of rent (housingBenefit) on {year}/{month}",
                    amount=MoneyAmount(JPY, -item.housingBenefitNonTaxable),
                    account=matched.account,
                    originalFormat=originalFormat,
                    sourceLocation=item.sourceLocation,
                    category=RENT,
                    amountIsRaw=True)
            )

        if item.reimbursement != 0:
            synthesizedForThisItem.append(
                synthesizedTransaction(
                    date=item.date,
                    description=f"Synthesized transaction: reimbursement through payslip on {year}/{month}",
                    amount=MoneyAmount(JPY, item.reimbursement),
                    account=matched.account,
                    originalFormat=originalFormat,
                    sourceLocation=item.sourceLocation,
                    category=REFUND_REIMBURSEMENT,
                    amountIsRaw=True))
        if item.localTax > 0:
            synthesizedForThisItem.append(
                synthesizedTransaction(
                    date=item.date,
                    description=f"Synthesized transaction: local tax deduction on {year}/{month}",
                    amount=MoneyAmount(JPY, -item.localTax),
                    account=matched.account,
                    originalFormat=originalFormat,
                    sourceLocation=item.sourceLocation,
                    category=LOCAL_TAX_DEDUCTION,
                    amountIsRaw=True))
        assert (
            sumSingleCurrencyAmounts(t.adjustedAmount for t in synthesizedForThisItem) ==
            MoneyAmount(JPY, item.payable + item.pensionVoluntary)
        )
        # TODO: maybe handle year end adjustments better, but it's already reflected in payable.
        allNewSynthesizedTransactions.extend(synthesizedForThisItem)

    return sortedByDate(remaining + allNewSynthesizedTransactions)
