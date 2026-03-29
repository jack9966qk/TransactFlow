from collections import defaultdict
from ..base import *
from datetime import timedelta
from itertools import product
from ..multiCurrency import totalAdjustedAmountAsJPY
from ..process import Process, funcProcess, sortByDateAndMore, LazyGroupedProcess
from ..userConfig import forceReadUserConfig

def forecastMonthlyTransactions(
    targetYear: int
) -> Process:
    def estimatedAmountFromPast365Days(
        category: Category,
        transactions: List[Transaction],
        untilDate: Date,
    ) -> MoneyAmount:
        fromDate = untilDate - timedelta(days=365)
        matchedTransactions = [
            t for t in transactions
            if fromDate <= t.date < untilDate and t.category == category
        ]
        assert(not any(t.isForecast for t in matchedTransactions))
        return MoneyAmount(JPY, totalAdjustedAmountAsJPY(matchedTransactions)) / 12

    @funcProcess(f"forecastMonthlyTransactions for year {targetYear}")
    def addMonthlyTransactions(transactions: List[Transaction]) -> List[Transaction]:
        transactionsInYear = [t for t in transactions if t.date.year == targetYear]
        lastestSalaryMonth = max(t.date.month for t in transactionsInYear if t.category == SALARY)
        addForecastMonthRange = range(lastestSalaryMonth + 1, 13)
        def generateConsumptionTransactions() -> Generator[Transaction]:
            def isCategoryForConsumption(c: Category) -> bool:
                return (
                    c.isUnder(EXPENSE) and
                    not c.isUnder(RENT) and
                    not c.isUnder(SOCIAL_SECURITY) and
                    not c.isUnder(MISC_INCOME_DEDUCTION) and
                    not c.isUnder(TAX)
                )
            consumptionCategories = [
                c for c in ORDERED_BASE_CATEGORIES if isCategoryForConsumption(c)
            ]
            assert(len(set(consumptionCategories)) == len(consumptionCategories))
            for month in addForecastMonthRange:
                for cat in consumptionCategories:
                    estimatedAmount = estimatedAmountFromPast365Days(
                        category=cat,
                        transactions=transactions,
                        untilDate=Date(year=targetYear, month=lastestSalaryMonth, day=1))
                    yield synthesizedTransaction(
                        date=Date(year=targetYear, month=month, day=25),
                        description=f"Synthesized forecasted {cat.label}",
                        amount=estimatedAmount,
                        category=cat,
                        account=PSEUDO_ACCOUNT,
                        isForecast=True)
        def generateSalaryRelatedTransactions() -> Generator[Transaction]:
            salaryRelatedCategories: List[Category] = [
                SALARY,
                NON_TAXABLE_SALARY_HOUSING_BENEFIT,
                NATIONAL_TAX_WITHHOLDING_SALARY,
                WELFARE_SALARY,
                HELATH_INSURANCE_SALARY,
                UNEMPL_INS_SALARY,
                MISC_INCOME_DEDUCTION_SALARY,
                PENSION_CONTRIBUTION,
                RENT,
                LOCAL_TAX_DEDUCTION,
            ]
            estimationStartMonth = 1 if lastestSalaryMonth < 3 else 3
            numEstimationMonths = 0
            totalAmountsForEstimation: Dict[Category, MoneyAmount] = {
                cat: EMPTY_AMOUNT for cat in salaryRelatedCategories
            }
            for month in range(estimationStartMonth, lastestSalaryMonth + 1):
                exactMatches = groupAsDict(
                    (
                        t for t in transactionsInYear
                        if t.date.month == month and
                        t.category in salaryRelatedCategories
                    ),
                    keyFn=lambda t: t.category
                )
                hasMissingCategory = any(
                    cat for cat in salaryRelatedCategories
                    if len(exactMatches.get(cat, [])) == 0
                )
                if hasMissingCategory:
                    # Break the loop so that estimation range effectively ends at the last month
                    # where all categories have matches.
                    break
                for cat in salaryRelatedCategories:
                    totalAmountsForEstimation[cat] += sum(
                        (t.adjustedAmount for t in exactMatches[cat]), start=EMPTY_AMOUNT
                    )
                numEstimationMonths += 1
            if numEstimationMonths == 0:
                # Estimation is not possible because there is not any month where amount for all
                # salary related categories can be obtained.
                assert(False)
            estimatedAmountForCategory = {
                cat: totalAmountsForEstimation[cat] / numEstimationMonths
                for cat in salaryRelatedCategories
            }
            for cat, estimatedAmount in estimatedAmountForCategory.items():
                for month in addForecastMonthRange:
                    yield synthesizedTransaction(
                        date=Date(year=targetYear, month=month, day=25),
                        description=f"Synthesized forecasted {cat.label}",
                        amount=estimatedAmount,
                        category=cat,
                        account=PSEUDO_ACCOUNT,
                        isForecast=True)
        return sortByDateAndMore(
            transactions +
            list(generateConsumptionTransactions()) +
            list(generateSalaryRelatedTransactions())
        )
    return addMonthlyTransactions


def _buildForecastProcesses() -> List[Process]:
    targetYear = forceReadUserConfig().forecast.targetYear
    return [forecastMonthlyTransactions(targetYear=targetYear)]


process = LazyGroupedProcess(label="Forecast", buildProcesses=_buildForecastProcesses)
