from transactflow.base import EMPLOYER, RENT, CASH_OUT
from transactflow.process import splitIntoTimeSectionsBySalaryIncome, minMaxDateOf, earnedIncomesOf, expensesOf
from transactflow.processes.runAll import run

def banner(name):
    return "=" * 40 + f"{name:^20s}" + "=" * 40

def report(transactions, name):
    print(banner(name))
    for t in transactions:
        print(t)
    print(banner(name))
    print("\n\n")

def printIncomeAndExpense(result, name):
    print(banner(name))
    resultWithCat = [t for t in result if t.category != None]
    earnedIncomes = earnedIncomesOf(resultWithCat)
    expenses = expensesOf(resultWithCat)
    print("Earned incomes:")
    for t in earnedIncomes: print(t)
    earnedIncomesTotal = sum([abs(t.rawAmount) for t in earnedIncomes])
    print(f"Total: {earnedIncomesTotal}")
    print("\n\nExpenses:")
    for t in expenses: print(t)
    expensesTotal = sum([abs(t.rawAmount) for t in expenses])
    print(f"Total: {expensesTotal}")
    print(f"\n{earnedIncomesTotal} - {expensesTotal} = {earnedIncomesTotal - expensesTotal}")
    print(banner(name))
    print("\n\n")

trans = run()
trans.sort(key=lambda t: t.date)
for t in trans:
    print(t)

# noCatOnly = filterProc(lambda t: t.category == None)
# noCatOnlyResult = applyProcesses(result, [noCatOnly])
# print("\n\nNo category defined:")
# for t in noCatOnlyResult:
#     print(t)

printIncomeAndExpense(trans, "All")

groups, leading = splitIntoTimeSectionsBySalaryIncome(trans)
minDate, maxDate = minMaxDateOf(leading)
description = f"From {minDate} to {maxDate} (Leading)"
printIncomeAndExpense(leading, description)
for group in groups:
    minDate, maxDate = minMaxDateOf(group)
    description = f"From {minDate} to {maxDate}"
    printIncomeAndExpense(group, description)

report([t for t in trans if t.relatedTo == EMPLOYER], "Employer")
report([t for t in trans if t.category == RENT], "Rent")
report([t for t in trans if t.category == CASH_OUT], "Cash Out")

# from analysis import AnalysisProvider, AnalysisProviderOptions, DeductSalaryOption
# provider = AnalysisProvider(trans, groups)
# options = AnalysisProviderOptions(labelOption="All")
# pieChartData = provider.pieChartData(options, DeductSalaryOption.NO_DEDUCTION, True)
# print(pieChartData)
# barChartData = provider.barChartData(options, DeductSalaryOption.NO_DEDUCTION)
# print(barChartData)