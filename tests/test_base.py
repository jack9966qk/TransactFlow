"""Tests for base data structures."""

from datetime import date
from transactflow.base import (
    Category, Transaction, MoneyAmount, ExchangeRates,
    EXPENSE, INCOME, SALARY, JPY, USD, STOCK_UNIT,
    EMPTY_AMOUNT, EMPTY_EXCHANGE_RATES, EMPTY_CURRENCY,
    SMBC_PRESTIA, EMPLOYER,
    syntheticTransaction, sortedByDate,
    sumSingleCurrencyAmounts, amountsHaveSameCurrency,
    splitIntoTimeSectionsBySalaryIncome,
    groupAsDict, concat, mapOptional,
    amountDeltaIsNegligible, SegmentedTotals,
)


class TestMoneyAmount:
    def test_add_same_currency(self):
        a = MoneyAmount(JPY, 1000)
        b = MoneyAmount(JPY, 2000)
        assert (a + b) == MoneyAmount(JPY, 3000)

    def test_add_with_empty(self):
        a = MoneyAmount(JPY, 1000)
        assert (a + EMPTY_AMOUNT) == a
        assert (EMPTY_AMOUNT + a) == a

    def test_subtract(self):
        a = MoneyAmount(JPY, 3000)
        b = MoneyAmount(JPY, 1000)
        assert (a - b) == MoneyAmount(JPY, 2000)

    def test_multiply(self):
        a = MoneyAmount(JPY, 1000)
        assert (a * 3) == MoneyAmount(JPY, 3000)

    def test_divide(self):
        a = MoneyAmount(JPY, 3000)
        assert (a / 3) == MoneyAmount(JPY, 1000)

    def test_negate(self):
        a = MoneyAmount(JPY, 1000)
        assert (-a) == MoneyAmount(JPY, -1000)

    def test_abs(self):
        a = MoneyAmount(JPY, -1000)
        assert abs(a) == MoneyAmount(JPY, 1000)

    def test_str(self):
        a = MoneyAmount(JPY, 1500)
        assert str(a) == "1500 JPY"

    def test_equality_zero_amounts(self):
        a = MoneyAmount(JPY, 0)
        b = MoneyAmount(USD, 0)
        assert a == b


class TestCategory:
    def test_hierarchy(self):
        assert SALARY.isUnder(INCOME)
        assert not SALARY.isUnder(EXPENSE)

    def test_depth(self):
        assert INCOME.depth == 0
        assert SALARY.depth > 0

    def test_ancestor_by(self):
        assert SALARY.ancestorBy(0) == SALARY
        assert SALARY.ancestorBy(100) is not None  # walks to root


class TestTransaction:
    def _make_transaction(self, amount=1000, category=INCOME):
        return Transaction(
            date=date(2025, 1, 15),
            description="Test transaction",
            rawAmount=MoneyAmount(JPY, amount),
            account=SMBC_PRESTIA,
            rawRecord="test,row",
            sourceLocation=("test.csv", 1),
            category=category,
            relatedTo=EMPLOYER,
        )

    def test_adjusted_amount_no_adjustments(self):
        t = self._make_transaction()
        assert t.adjustedAmount == MoneyAmount(JPY, 1000)

    def test_adjusted_amount_with_adjustment(self):
        t = self._make_transaction().addingAdjustment(500)
        assert t.adjustedAmount == MoneyAmount(JPY, 1500)

    def test_replacing_category(self):
        t = self._make_transaction()
        t2 = t.replacingCategory(EXPENSE)
        assert t2.category == EXPENSE
        assert t.category == INCOME  # original unchanged

    def test_replacing_account(self):
        t = self._make_transaction()
        t2 = t.replacingAccount("New Account")
        assert t2.account == "New Account"

    def test_synthetic_transaction(self):
        t = syntheticTransaction(
            date=date(2025, 3, 1),
            description="Synth",
            amount=MoneyAmount(JPY, 5000),
            category=EXPENSE,
            account=SMBC_PRESTIA,
        )
        assert t.adjustedAmount == MoneyAmount(JPY, 5000)
        assert t.rawAmount == MoneyAmount(JPY, 0)


class TestUtilities:
    def test_sorted_by_date(self):
        t1 = syntheticTransaction(date=date(2025, 3, 1), description="c",
                                    amount=MoneyAmount(JPY, 0), category=EXPENSE, account="A")
        t2 = syntheticTransaction(date=date(2025, 1, 1), description="a",
                                    amount=MoneyAmount(JPY, 0), category=EXPENSE, account="A")
        t3 = syntheticTransaction(date=date(2025, 2, 1), description="b",
                                    amount=MoneyAmount(JPY, 0), category=EXPENSE, account="A")
        result = sortedByDate([t1, t2, t3])
        assert [t.description for t in result] == ["a", "b", "c"]

    def test_sum_single_currency(self):
        amounts = [MoneyAmount(JPY, 100), MoneyAmount(JPY, 200), MoneyAmount(JPY, 300)]
        assert sumSingleCurrencyAmounts(amounts) == MoneyAmount(JPY, 600)

    def test_amounts_have_same_currency(self):
        assert amountsHaveSameCurrency([MoneyAmount(JPY, 1), MoneyAmount(JPY, 2)])
        assert not amountsHaveSameCurrency([MoneyAmount(JPY, 1), MoneyAmount(USD, 2)])

    def test_concat(self):
        assert concat([[1, 2], [3], [4, 5]]) == [1, 2, 3, 4, 5]

    def test_group_as_dict(self):
        result = groupAsDict(iter([1, 2, 3, 4]), lambda x: x % 2)
        assert result[0] == [2, 4]
        assert result[1] == [1, 3]

    def test_map_optional(self):
        assert mapOptional(5, lambda x: x * 2) == 10
        assert mapOptional(None, lambda x: x * 2) is None

    def test_amount_delta_negligible(self):
        assert amountDeltaIsNegligible(MoneyAmount(JPY, 50))
        assert not amountDeltaIsNegligible(MoneyAmount(JPY, 200))
        assert amountDeltaIsNegligible(MoneyAmount(USD, 0.5))
        assert not amountDeltaIsNegligible(MoneyAmount(USD, 2))
