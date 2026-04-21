import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from dateutil.parser import parse as parseDate

from ..base import *
from ..multiCurrency import MultiCurrencyAmount
from ..process import Process, funcMatching, funcProcess, takeFirstMatch
from ..processes.payslipAnnotationItem import PayslipAnnotationItem


@dataclass
class PayslipAnnotationItemParserState:
    date: Date
    type: str
    sourceLocation: Optional[Tuple[str, int]] = None
    gross: float = 0
    healthInsurance: float = 0
    welfare: float = 0
    unemplIns: float = 0
    pensionVoluntary: float = 0
    nationalTax: float = 0
    localTax: float = 0
    yearEndAdj: float = 0
    miscDeduction: float = 0
    housingBenefitTaxable: float = 0
    housingBenefitNonTaxable: float = 0
    reimbursement: float = 0
    payable: float = 0

    def convertToAnnotation(self) -> PayslipAnnotationItem:
        return PayslipAnnotationItem(
            sourceLocation=self.sourceLocation,
            date=self.date,
            type=self.type,
            gross=self.gross,
            healthInsurance=self.healthInsurance,
            welfare=self.welfare,
            unemplIns=self.unemplIns,
            pensionVoluntary=self.pensionVoluntary,
            nationalTax=self.nationalTax,
            localTax=self.localTax,
            yearEndAdj=self.yearEndAdj,
            miscDeduction=self.miscDeduction,
            housingBenefitTaxable=self.housingBenefitTaxable,
            housingBenefitNonTaxable=self.housingBenefitNonTaxable,
            reimbursement=self.reimbursement,
            payable=self.payable
        )

def payslipAnnotationsFromTSV(
    tsvPath: Path,
    datesPath: Path,
    updateParserState: Callable[[PayslipAnnotationItemParserState, Dict[str, str]]]
) -> List[PayslipAnnotationItem]:
    paymentTypes = ["Payroll", "Bonus"]
    dates = iter([
        parseDate(s).date()
        for s in datesPath.read_text().split("\n") if len(s) > 0
    ])
    activeDate: Date | None = None
    paymentTypesToParserStateForMonth: dict[
        tuple[int, int], dict[str, PayslipAnnotationItemParserState]
    ] = defaultdict(dict)
    with open(tsvPath) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            year = int(row["Year"])
            month = int(row["Month"])
            paymentType = row["Type"]
            assert paymentType in paymentTypes
            parserStatesByType = paymentTypesToParserStateForMonth[(year, month)]
            parserState = parserStatesByType.get(paymentType, None)
            if parserState is None:
                activeDate = next(dates)
                if paymentType == "Payroll":
                    annotationType = "salary"
                elif paymentType == "Bonus":
                    annotationType = "bonus"
                else:
                    assert(False)
                parserState = PayslipAnnotationItemParserState(
                    date=activeDate,
                    type=annotationType,
                    sourceLocation=(str(tsvPath), reader.line_num))
                parserStatesByType[paymentType] = parserState
            assert activeDate is not None
            assert activeDate.year == year
            assert activeDate.month == month
            updateParserState(parserState, row)
    def genAnnotationItems():
        months = sorted(paymentTypesToParserStateForMonth.keys())
        for yearMonth in months:
            parserStatesByType = paymentTypesToParserStateForMonth[yearMonth]
            for paymentType in paymentTypes:
                if paymentType not in parserStatesByType: continue
                yield parserStatesByType[paymentType].convertToAnnotation()
    return list(genAnnotationItems())

def expectedTotalBalanceDelta(annotations: List[PayslipAnnotationItem]) -> MultiCurrencyAmount:
    totalPensionVoluntaryQuantity = sum(item.pensionVoluntary for item in annotations)
    return MultiCurrencyAmount(quantities={JPY: totalPensionVoluntaryQuantity})

def makePayslipAnnotationsProcess(annotations: List[PayslipAnnotationItem]) -> Process:
    """
    Read payslip annotation file and update the salary and bonus transactions with more details.
    Specifically:
        - For each payslip item, match a salary/bonus transaction and replace it
        - Verify that "payable" under each payslip item matches the corresponding transaction
          (each payslip item is internally consistent, verified upon init)
        - Add synthetic transactions for all gross income and its deduction items
    """
    @funcProcess("applyPayslipAnnotations")
    def applyPayslipAnnotations(transactions: List[Transaction]) -> List[Transaction]:
        if len(annotations) == 0:
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
    return applyPayslipAnnotations
