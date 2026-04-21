from typing import Generator, Iterator, List

from ..base import *
from ..base import StockUnit
from ..capitalGainCalculation import Activity, Sell, Vest, genCapitalGain
from ..process import Process, funcProcess, sortByDateAndMore


def addCaptialGainProcess(stockUnit: StockUnit) -> Process:
    @funcProcess()
    def addCapitalGain(transactions: List[Transaction]) -> List[Transaction]:
        def genTransactions(iterator: Iterator[Transaction]) -> Generator[Transaction, None, None]:
            # There is a trade off between calculating this in USD and in JPY. Delta in USD is a
            # better match for reality, but Japan tax for capital gain is measured using JPY prices
            # at each activity, even though it may capture unrealized gain/loss from USDJPY
            # conversions.
            # Using JPY for now, assuming the intended use case is to help Japan tax redistribution
            # and to run analysis with JPY as the target currency.
            calculator = genCapitalGain(inUSD=False)
            next(calculator)
            for transaction in iterator:
                yield transaction
                if transaction.isForecast: continue
                rates = transaction.referencedExchangeRates
                USDPerShare = rates.USDPerStockUnitShare
                USDJPYRate = rates.USDJPYRate
                if (
                    transaction.category == EQUITY_VESTING and
                    transaction.rawAmount.currency == stockUnit
                ):
                    assert(USDPerShare is not None)
                    assert(USDJPYRate is not None)
                    vestActivity = Activity(
                        vestOrSell=Vest(
                            priceUSD=USDPerShare,
                            rateUSDJPY=USDJPYRate,
                            numUnits=transaction.rawAmount.quantity),
                        date=transaction.date)
                    empty = calculator.send(vestActivity)
                    assert(empty is None)
                elif (
                    transaction.category == CURRENCY_CONVERSION_SENT and
                    transaction.rawAmount.currency == stockUnit
                ):
                    assert(USDPerShare is not None)
                    assert(USDJPYRate is not None)
                    numUnits = abs(transaction.rawAmount.quantity)
                    sellActivity = Activity(
                        vestOrSell=Sell(
                            priceUSD=USDPerShare,
                            rateUSDJPY=USDJPYRate,
                            numUnits=numUnits),
                        date=transaction.date)
                    gainEntry = calculator.send(sellActivity)
                    assert(gainEntry is not None)
                    gainAmount = gainEntry.gainAmount
                    assert(gainAmount > 0)
                    yield syntheticTransaction(
                        date=transaction.date,
                        description=f"Synthetic capital gain from selling {numUnits} Stock Units",
                        amount=MoneyAmount(JPY, gainEntry.gainAmount),
                        account=transaction.account,
                        category=CAPITAL_GAIN,
                        rawRecord=transaction.rawRecord,
                        relatedTo=transaction.relatedTo,
                        sourceLocation=transaction.sourceLocation,
                        referencedExchangeRates=transaction.referencedExchangeRates)
        iterator = iter(sortByDateAndMore(transactions))
        # capitalGainCalculation.DEBUG = True
        result = list(genTransactions(iterator))
        # breakpoint()
        return result
    return addCapitalGain
