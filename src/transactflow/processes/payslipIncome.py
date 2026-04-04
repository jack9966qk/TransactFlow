from typing import List
from ..base import *
from ..multiCurrency import MultiCurrencyAmount
from ..process import funcMatching, funcProcess, takeFirstMatch
from ..processes.payslipAnnotationItem import PayslipAnnotationItem
from ..userConfig import forceReadUserConfig

def readPayslipAnnotations() -> List[PayslipAnnotationItem]:
    config = forceReadUserConfig().processes
    if config is None: return []
    annotations = config.payslipAnnotations
    if annotations is None: return []
    return annotations

def expectedTotalBalanceDelta() -> MultiCurrencyAmount:
    totalPensionVoluntaryQuantity = sum(item.pensionVoluntary for item in readPayslipAnnotations())
    return MultiCurrencyAmount(quantities={JPY: totalPensionVoluntaryQuantity})

@funcProcess()
def applyPayslipAnnotations(transactions: List[Transaction]) -> List[Transaction]:
    """
    Read payslip annotation file and update the salary and bonus transactions with more details.
    Specifically:
        - For each payslip item, match a salary/bonus transaction and replace it
        - Verify that "payable" under each payslip item matches the corresponding transaction
          (each payslip item is internally consistent, verified upon init)
        - Add synthetic transactions for all gross income and its deduction items
    """
    annotations = readPayslipAnnotations()
    if annotations is None or len(annotations) == 0:
        return transactions
    allNewSyntheticTransactions = []
    remaining = transactions
    for item in annotations:
        rawRecord = (
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
            HEALTH_INSURANCE_SALARY,
            UNEMPL_INS_SALARY,
            MISC_INCOME_DEDUCTION_SALARY) if incomeCategory == SALARY else (
            NATIONAL_TAX_WITHHOLDING_BONUS,
            WELFARE_BONUS,
            HEALTH_INSURANCE_BONUS,
            UNEMPL_INS_BONUS,
            MISC_INCOME_DEDUCTION_BONUS)
        syntheticForThisItem = [
            syntheticTransaction(
                date=item.date,
                description=f"Payslip {incomeCategory.label} income {year}/{month}",
                amount=MoneyAmount(JPY, item.gross - item.yearEndAdj - item.reimbursement - item.pensionVoluntary),
                account=matched.account,
                rawRecord=rawRecord,
                sourceLocation=item.sourceLocation,
                category=incomeCategory,
                amountIsRaw=True),
            syntheticTransaction(
                date=item.date,
                description=f"Synthetic transaction: health insurance deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.healthInsurance),
                account=matched.account,
                rawRecord=rawRecord,
                sourceLocation=item.sourceLocation,
                category=healthInsCat,
                amountIsRaw=True),
            syntheticTransaction(
                date=item.date,
                description=f"Synthetic transaction: welfare deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.welfare),
                account=matched.account,
                rawRecord=rawRecord,
                sourceLocation=item.sourceLocation,
                category=welfareCat,
                amountIsRaw=True),
            syntheticTransaction(
                date=item.date,
                description=f"Synthetic transaction: unempl. ins deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.unemplIns),
                account=matched.account,
                rawRecord=rawRecord,
                sourceLocation=item.sourceLocation,
                category=unemplInsCat,
                amountIsRaw=True),
            syntheticTransaction(
                date=item.date,
                description=f"Synthetic transaction: misc income deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.miscDeduction),
                account=matched.account,
                rawRecord=rawRecord,
                sourceLocation=item.sourceLocation,
                category=miscDeductionCat,
                amountIsRaw=True),
            syntheticTransaction(
                date=item.date,
                description=f"Synthetic transaction: national tax deduction on {year}/{month}",
                amount=MoneyAmount(JPY, -item.nationalTax),
                account=matched.account,
                rawRecord=rawRecord,
                sourceLocation=item.sourceLocation,
                category=withholdingCat,
                amountIsRaw=True),
        ]

        if item.pensionVoluntary > 0:
            syntheticForThisItem.append(
                syntheticTransaction(
                    date=item.date,
                    description=f"Synthetic transaction: Pension voluntary contribution on {year}/{month}",
                    amount=MoneyAmount(JPY, item.pensionVoluntary),
                    account=PENSION,
                    rawRecord=rawRecord,
                    sourceLocation=item.sourceLocation,
                    category=PENSION_CONTRIBUTION,
                    relatedTo=EMPLOYER,
                    amountIsRaw=True)
            )

        if item.housingBenefitTaxable > 0:
            syntheticForThisItem.append(
                syntheticTransaction(
                    date=item.date,
                    description=f"Synthetic transaction: taxable portion of rent (housingBenefit) on {year}/{month}",
                    amount=MoneyAmount(JPY, -item.housingBenefitTaxable),
                    account=matched.account,
                    rawRecord=rawRecord,
                    sourceLocation=item.sourceLocation,
                    category=RENT,
                    amountIsRaw=True),
            )
        if item.housingBenefitNonTaxable > 0:
            syntheticForThisItem.append(
                syntheticTransaction(
                    date=item.date,
                    description=f"Synthetic transaction: non taxable salary for housingBenefit on {year}/{month}",
                    amount=MoneyAmount(JPY, item.housingBenefitNonTaxable),
                    account=matched.account,
                    rawRecord=rawRecord,
                    sourceLocation=item.sourceLocation,
                    category=NON_TAXABLE_SALARY_HOUSING_BENEFIT,
                    amountIsRaw=True)
            )
            syntheticForThisItem.append(
                syntheticTransaction(
                    date=item.date,
                    description=f"Synthetic transaction: non-taxable portion of rent (housingBenefit) on {year}/{month}",
                    amount=MoneyAmount(JPY, -item.housingBenefitNonTaxable),
                    account=matched.account,
                    rawRecord=rawRecord,
                    sourceLocation=item.sourceLocation,
                    category=RENT,
                    amountIsRaw=True)
            )

        if item.reimbursement != 0:
            syntheticForThisItem.append(
                syntheticTransaction(
                    date=item.date,
                    description=f"Synthetic transaction: reimbursement through payslip on {year}/{month}",
                    amount=MoneyAmount(JPY, item.reimbursement),
                    account=matched.account,
                    rawRecord=rawRecord,
                    sourceLocation=item.sourceLocation,
                    category=REFUND_REIMBURSEMENT,
                    amountIsRaw=True))
        if item.localTax > 0:
            syntheticForThisItem.append(
                syntheticTransaction(
                    date=item.date,
                    description=f"Synthetic transaction: local tax deduction on {year}/{month}",
                    amount=MoneyAmount(JPY, -item.localTax),
                    account=matched.account,
                    rawRecord=rawRecord,
                    sourceLocation=item.sourceLocation,
                    category=LOCAL_TAX_DEDUCTION,
                    amountIsRaw=True))
        assert (
            sumSingleCurrencyAmounts(t.adjustedAmount for t in syntheticForThisItem) ==
            MoneyAmount(JPY, item.payable + item.pensionVoluntary)
        )
        # TODO: maybe handle year end adjustments better, but it's already reflected in payable.
        allNewSyntheticTransactions.extend(syntheticForThisItem)

    return sortedByDate(remaining + allNewSyntheticTransactions)
