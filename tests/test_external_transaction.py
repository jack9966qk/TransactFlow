from datetime import date

from transactflow.base import (
    Category, Currency, ExchangeRates, MoneyAmount, Transaction,
    EMPTY_EXCHANGE_RATES, JPY, USD, EXPENSE, INCOME, RENT,
)
from transactflow.externalTransaction import (
    fromExternalTransaction, toExternalTransaction,
)


def _makeTransaction(**overrides) -> Transaction:
    defaults = dict(
        date=date(2025, 6, 15),
        description="Groceries",
        rawAmount=MoneyAmount(JPY, -3000),
        account="SMBC Prestia",
        originalFormat="prestia",
        sourceLocation=("importers/prestia.py", 42),
        category=EXPENSE,
        relatedTo=None,
        adjustments=(),
        comment=None,
        referencedExchangeRates=EMPTY_EXCHANGE_RATES,
        isUnrealized=False,
        isForecast=False,
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def _assertTransactionsEqual(a: Transaction, b: Transaction):
    assert a.date == b.date
    assert a.description == b.description
    assert a.rawAmount.currency == b.rawAmount.currency
    assert a.rawAmount.quantity == b.rawAmount.quantity
    assert a.account == b.account
    assert a.originalFormat == b.originalFormat
    assert a.sourceLocation == b.sourceLocation
    assert a.relatedTo == b.relatedTo
    assert a.adjustments == b.adjustments
    assert a.comment == b.comment
    assert a.referencedExchangeRates == b.referencedExchangeRates
    assert a.isUnrealized == b.isUnrealized
    assert a.isForecast == b.isForecast
    # Category: compare labels and hierarchy
    assert a.category.label == b.category.label
    assert (a.category.parent is None) == (b.category.parent is None)
    if a.category.parent is not None:
        assert a.category.parent.label == b.category.parent.label


class TestRoundTrip:
    def test_basicTransaction(self):
        tx = _makeTransaction()
        result = fromExternalTransaction(toExternalTransaction(tx))
        _assertTransactionsEqual(tx, result)

    def test_withAllOptionalFields(self):
        tx = _makeTransaction(
            relatedTo="Employer",
            adjustments=(500.0, -200.0),
            comment="Reimbursement pending",
            referencedExchangeRates=ExchangeRates(USDJPYRate=149.5, USDPerStockUnitShare=None),
        )
        result = fromExternalTransaction(toExternalTransaction(tx))
        _assertTransactionsEqual(tx, result)

    def test_noSourceLocation(self):
        tx = _makeTransaction(sourceLocation=None)
        result = fromExternalTransaction(toExternalTransaction(tx))
        _assertTransactionsEqual(tx, result)

    def test_hierarchicalCategory(self):
        tx = _makeTransaction(category=RENT)
        result = fromExternalTransaction(toExternalTransaction(tx))
        assert result.category.label == "Rent"
        assert result.category.parent is not None
        assert result.category.parent.label == "General Expense"

    def test_exchangeRatesBothSet(self):
        tx = _makeTransaction(
            rawAmount=MoneyAmount(USD, 100.0),
            referencedExchangeRates=ExchangeRates(
                USDJPYRate=150.0, USDPerStockUnitShare=200.0
            ),
        )
        result = fromExternalTransaction(toExternalTransaction(tx))
        assert result.referencedExchangeRates.USDJPYRate == 150.0
        assert result.referencedExchangeRates.USDPerStockUnitShare == 200.0

    def test_serializedBytesRoundTrip(self):
        """Verify that serializing to bytes and back also works."""
        tx = _makeTransaction(
            relatedTo="Family",
            adjustments=(1000.0,),
            comment="Gift",
        )
        proto = toExternalTransaction(tx)
        serialized = proto.SerializeToString()
        from transactflow.proto_gen.transactflow_pb2 import ExternalTransaction
        restored = ExternalTransaction()
        restored.ParseFromString(serialized)
        result = fromExternalTransaction(restored)
        _assertTransactionsEqual(tx, result)

    def test_unrealizedTransaction(self):
        tx = _makeTransaction(
            rawAmount=MoneyAmount(USD, 0),
            adjustments=(500.0,),
            isUnrealized=True,
        )
        result = fromExternalTransaction(toExternalTransaction(tx))
        _assertTransactionsEqual(tx, result)
        assert result.isUnrealized is True

    def test_forecastTransaction(self):
        tx = _makeTransaction(
            rawAmount=MoneyAmount(JPY, 0),
            adjustments=(-50000.0,),
            isForecast=True,
        )
        result = fromExternalTransaction(toExternalTransaction(tx))
        _assertTransactionsEqual(tx, result)
        assert result.isForecast is True
