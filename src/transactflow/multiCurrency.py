from dataclasses import dataclass
from functools import reduce
from typing import Iterable, Optional

from .base import *
from .base import StockUnit
from .rates import getOrRetrieveLatestRates

@dataclass(frozen=True)
class MultiCurrencyAmount:
    quantities: dict[Currency, float]

    def __add__(self, other: "MultiCurrencyAmount"):
        newQuantities = dict(self.quantities)
        for c, q in other.quantities.items():
            newQuantities[c] = newQuantities.get(c, 0) + q
        return MultiCurrencyAmount(newQuantities)

    def __sub__(self, other: "MultiCurrencyAmount"):
        return self + (-other)

    def __mul__(self, other: float):
        return MultiCurrencyAmount({c: q * other for c, q in self.quantities.items()})

    def __abs__(self):
        return MultiCurrencyAmount({c: abs(q) for c, q in self.quantities.items()})

    def __neg__(self):
        return self * -1

    def __eq__(self, other: "MultiCurrencyAmount"):
        return self.pruningZeroes().quantities == other.pruningZeroes().quantities

    @property
    def longDescription(self) -> str:
        if len(self.quantities) == 0: return f"{'Empty':>10}"
        sortedCurrencies = sorted(set(c for c in self.quantities.keys()), key=lambda c: c.label)
        return "\n".join(f"{c.label:>10}: {self.quantities[c]:,.2f}" for c in sortedCurrencies)

    def addingAmount(self, amount: MoneyAmount) -> "MultiCurrencyAmount":
        return self + MultiCurrencyAmount({amount.currency: amount.quantity})

    def pruningZeroes(self) -> "MultiCurrencyAmount":
        return MultiCurrencyAmount({
            c: q for c, q in self.quantities.items() if q != 0
        })

    def aggregatedUsingLatestRatesAs(self, currency: Currency) -> float:
        rates = getOrRetrieveLatestRates()
        amount = 0
        for c, q in self.quantities.items():
            amount += rates.rate(convertFrom=c, to=currency) * q
        return amount

    @property
    def isEmpty(self) -> bool: return len(self.quantities) == 0

def sumCurrencyAmounts(amounts: Iterable[MoneyAmount]) -> MultiCurrencyAmount:
    return reduce(
        lambda a, b: a + MultiCurrencyAmount({b.currency: b.quantity}),
        amounts,
        MultiCurrencyAmount({})
    ).pruningZeroes()

def totalRawAmount(transactions: Iterable[Transaction]) -> MultiCurrencyAmount:
    return sumCurrencyAmounts(t.rawAmount for t in transactions)

def totalAdjustedAmount(transactions: Iterable[Transaction]) -> MultiCurrencyAmount:
    return sumCurrencyAmounts(t.adjustedAmount for t in transactions)

def amountInJPY(amount: MoneyAmount, exchangeRates: Optional[ExchangeRates] = None) -> float:
    if amount.currency == JPY: return amount.quantity
    assert(exchangeRates is not None)
    if isinstance(amount.currency, StockUnit):
        assert((USDJPYRate := exchangeRates.USDJPYRate) is not None)
        assert((USDPerShare := exchangeRates.USDPerStockUnitShare) is not None)
        return USDPerShare * USDJPYRate * amount.quantity
    if amount.currency == USD:
        assert((USDJPYRate := exchangeRates.USDJPYRate) is not None)
        return USDJPYRate * amount.quantity
    # TODO: Add support for other scenarios.
    assert(False)

def embeddedOrLatestRatesFor(transaction: Transaction) -> Optional[ExchangeRates]:
    rates = transaction.referencedExchangeRates
    if (
        rates.USDJPYRate is None and
        rates.USDPerStockUnitShare is None and
        isinstance(transaction.rawAmount.currency, StockUnit)
        # and transaction.date > Date.today()
    ):
        # if transaction.date <= Date.today():
            # print(f"WARNING: using latest rates for transaction at {transaction.date}")
        retrievedRates = getOrRetrieveLatestRates()
        stockUnit = transaction.rawAmount.currency
        assert isinstance(stockUnit, StockUnit)
        assert stockUnit in retrievedRates.stockUnitUSDPrices, (
            f"No retrieved rate for stock unit {stockUnit.label}"
        )
        return ExchangeRates(
            USDPerStockUnitShare=retrievedRates.stockUnitUSDPrices[stockUnit],
            USDJPYRate=retrievedRates.USDJPYRate
        )
    return rates

def totalAdjustedAmountAsJPY(transactions: Iterable[Transaction]) -> float:
    return sum(
        amountInJPY(t.adjustedAmount, embeddedOrLatestRatesFor(t))
        for t in transactions
    )

def totalRawAmountAsJPY(transactions: Iterable[Transaction]) -> float:
    return sum(
        amountInJPY(t.rawAmount, embeddedOrLatestRatesFor(t))
        for t in transactions
    )
