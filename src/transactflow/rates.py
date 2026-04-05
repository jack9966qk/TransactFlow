from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, cast
import pickle
import os
import yfinance
from .base import Date, Currency, JPY, USD, CNY, StockUnit
from .base import memo  # type: ignore

@dataclass(frozen=True)
class RetrivedRates:
    JPYCNYRate: float
    USDJPYRate: float
    stockUnitUSDPrices: dict[StockUnit, float]
    dateOfRetrieval: Date

    def rate(self, convertFrom: Currency, to: Currency) -> float:
        if convertFrom == to: return 1
        if convertFrom == JPY and to == CNY:
            return self.JPYCNYRate
        if convertFrom == USD and to == JPY:
            return self.USDJPYRate
        if isinstance(convertFrom, StockUnit):
            assert convertFrom in self.stockUnitUSDPrices, (
                f"No retrieved rate for stock unit {convertFrom.label}"
            )
            usdPerShare = self.stockUnitUSDPrices[convertFrom]
            if to == USD:
                return usdPerShare
            if to == JPY:
                return usdPerShare * self.USDJPYRate
        # Unsupported rates. TODO: add support.
        assert(False)

def currencyRate(fromCur: Currency, toCur: Currency) -> float:
    """
    Get up to date currency rate, at most 48 hours earlier than now.
    """
    # This one is sometimes unavailable.
    # from forex_python.converter import CurrencyRates
    # return float(CurrencyRates().get_rate(fromCur, toCur, today))
    # This one doesn't seem to give rate for today, the latest is about 10 days ago.
    # return CurrencyConverter().convert(1.0, fromCur, toCur, today)
    import requests
    api_key = os.getenv("EXCHANGERATE_API_KEY")
    assert(api_key is not None and type(api_key) == str)
    response = requests.request(
        "GET",
        f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{fromCur.label}/{toCur.label}",
    )
    responseJson = response.json()
    lastUpdateTime = datetime.utcfromtimestamp(responseJson["time_last_update_unix"])
    tdelta = datetime.now() - lastUpdateTime
    assert(tdelta.days < 2)
    return responseJson["conversion_rate"]

RATES_CACHE_PATH = "ratesCache.pickle"

# Also cache in memory, so that the file is only read once
RATES_IN_MEMORY: Optional[RetrivedRates] = None

def getOrRetrieveLatestRates(stockUnits: frozenset[StockUnit]) -> RetrivedRates:
    global RATES_IN_MEMORY
    if RATES_IN_MEMORY is None and os.path.exists(RATES_CACHE_PATH):
        with open(RATES_CACHE_PATH, "rb") as f:
            RATES_IN_MEMORY = pickle.load(f)
    now = datetime.now()
    today = Date(year=now.year, month=now.month, day=now.day)
    targetDay = today if now.hour > 4 else today - timedelta(days=1)
    if RATES_IN_MEMORY is not None and RATES_IN_MEMORY.dateOfRetrieval == targetDay:
        if len(stockUnits - frozenset(RATES_IN_MEMORY.stockUnitUSDPrices.keys())) > 0:
            assert False, "Using cached rates but it does not contain the requested stock units"
        return RATES_IN_MEMORY
    # Retrieve rates
    stockUnitUSDPrices: dict[StockUnit, float] = {}
    for unit in stockUnits:
        price = yfinance.Ticker(unit.label).history(period="1d")["Close"].iloc[-1]
        stockUnitUSDPrices[unit] = cast(float, price)
    RATES_IN_MEMORY = RetrivedRates(
        JPYCNYRate=currencyRate(JPY, CNY),
        USDJPYRate=currencyRate(USD, JPY),
        stockUnitUSDPrices=stockUnitUSDPrices,
        dateOfRetrieval=targetDay)
    with open(RATES_CACHE_PATH, "wb") as f:
        pickle.dump(RATES_IN_MEMORY, f)
    return RATES_IN_MEMORY
