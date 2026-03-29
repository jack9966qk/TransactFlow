"""Tests for the process module (matching, labelling, pipeline)."""

from datetime import date
from transactflow.base import (
    Transaction, MoneyAmount, Category,
    JPY, EXPENSE, INCOME, SALARY, SHOPPING, DAILY_SHOPPING, MAJOR_SHOPPING,
    SMBC_PRESTIA, EMPLOYER, GENERAL_EXPENSE_DESTINATION,
)
from transactflow.process import (
    matching, funcProcess, funcMatching, GroupedProcess,
    labelIfMatch, EVERYTHING, satisfyAll, satisfyAny,
    takeMatched, takeFirstMatch, mapProc, funcMapping,
    relabelShoppingAsDaily, relabelShoppingAsMajor,
    labelSalaryIncome, labelGeneralExpenseDestination,
)


def makeTransaction(
    amount=1000, category=INCOME, account=SMBC_PRESTIA,
    description="Test", year=2025, month=1, day=15,
    relatedTo=EMPLOYER,
):
    return Transaction(
        date=date(year, month, day),
        description=description,
        rawAmount=MoneyAmount(JPY, amount),
        account=account,
        originalFormat="test,row",
        sourceLocation=("test.csv", 1),
        category=category,
        relatedTo=relatedTo,
    )


class TestMatching:
    def test_match_by_account(self):
        t = makeTransaction(account=SMBC_PRESTIA)
        assert matching(account=SMBC_PRESTIA)(t)
        assert not matching(account="Other")(t)

    def test_match_by_year(self):
        t = makeTransaction(year=2025)
        assert matching(year=2025)(t)
        assert not matching(year=2024)(t)

    def test_match_by_desc_substr(self):
        t = makeTransaction(description="Monthly Rent Payment")
        assert matching(descSubstr="Rent")(t)
        assert not matching(descSubstr="Salary")(t)

    def test_match_by_amount_pos_neg(self):
        t_pos = makeTransaction(amount=1000)
        t_neg = makeTransaction(amount=-1000)
        assert matching(amountPosNegIs="pos")(t_pos)
        assert matching(amountPosNegIs="neg")(t_neg)

    def test_match_by_exact_category(self):
        t = makeTransaction(category=SALARY)
        assert matching(exactCategory=SALARY)(t)
        assert not matching(exactCategory=EXPENSE)(t)

    def test_match_by_date_range(self):
        t = makeTransaction(year=2025, month=2, day=15)
        assert matching(dateFrom=date(2025, 1, 1), dateUntil=date(2025, 3, 1))(t)
        assert not matching(dateFrom=date(2025, 3, 1))(t)


class TestSatisfyAllAny:
    def test_satisfy_all(self):
        t = makeTransaction(amount=1000, account=SMBC_PRESTIA)
        combined = satisfyAll([
            matching(account=SMBC_PRESTIA),
            matching(amountPosNegIs="pos"),
        ])
        assert combined(t)

    def test_satisfy_any(self):
        t = makeTransaction(account=SMBC_PRESTIA)
        combined = satisfyAny([
            matching(account="Other"),
            matching(account=SMBC_PRESTIA),
        ])
        assert combined(t)


class TestLabelIfMatch:
    def test_labels_category(self):
        t = makeTransaction(category=INCOME)
        process = labelIfMatch(EVERYTHING, category=SALARY)
        result = process([t])
        assert result[0].category == SALARY

    def test_labels_related_to(self):
        t = makeTransaction()
        process = labelIfMatch(EVERYTHING, relatedTo="Bank")
        result = process([t])
        assert result[0].relatedTo == "Bank"


class TestTakeMatched:
    def test_take_matched(self):
        t1 = makeTransaction(amount=1000)
        t2 = makeTransaction(amount=-500)
        t3 = makeTransaction(amount=2000)
        matched, remaining = takeMatched(
            [t1, t2, t3], matching(amountPosNegIs="pos"))
        assert len(matched) == 2
        assert len(remaining) == 1

    def test_take_first_match(self):
        t1 = makeTransaction(amount=1000)
        t2 = makeTransaction(amount=2000)
        first, remaining = takeFirstMatch(
            [t1, t2], matching(amountPosNegIs="pos"))
        assert first is not None
        assert first.rawAmount.quantity == 1000
        assert len(remaining) == 1


class TestGroupedProcess:
    def test_empty_grouped_process(self):
        gp = GroupedProcess(label="Empty", processes=[])
        assert gp([]) == []

    def test_chained_processes(self):
        @funcProcess("double")
        def double_amounts(transactions):
            return [t.addingAdjustment(t.rawAmount.quantity) for t in transactions]

        @funcProcess("add_one")
        def add_extra(transactions):
            return transactions + [makeTransaction(amount=999, description="Extra")]

        gp = GroupedProcess(label="Chain", processes=[add_extra, double_amounts])
        result = gp([makeTransaction()])
        assert len(result) == 2
        assert result[0].adjustedAmount.quantity == 2000
        assert result[1].adjustedAmount.quantity == 1998


class TestShoppingRelabelling:
    def test_daily_shopping(self):
        t = makeTransaction(amount=-5000, category=SHOPPING)
        result = relabelShoppingAsDaily([t])
        assert result[0].category == DAILY_SHOPPING

    def test_major_shopping(self):
        t = makeTransaction(amount=-15000, category=SHOPPING)
        result = relabelShoppingAsMajor([t])
        assert result[0].category == MAJOR_SHOPPING
