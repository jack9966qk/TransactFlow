from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, cast
import pickle
import os
import yfinance
from .base import Date, Currency, JPY, USD, CNY, STOCK_UNIT
from .base import memo  # type: ignore
from .userConfig import forceReadUserConfig

@dataclass(frozen=True)
class RetrivedRates:
    JPYCNYRate: float
    USDJPYRate: float
    USDPerStockUnitShare: float
    dateOfRetrieval: Date

    def rate(self, convertFrom: Currency, to: Currency) -> float:
        if convertFrom == to: return 1
        if convertFrom == JPY and to == CNY:
            return self.JPYCNYRate
        if convertFrom == USD and to == JPY:
            return self.USDJPYRate
        if convertFrom == STOCK_UNIT and to == USD:
            return self.USDPerStockUnitShare
        if convertFrom == STOCK_UNIT and to == JPY:
            return self.USDPerStockUnitShare * self.USDJPYRate
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
    response = requests.request("GET",
                                f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{fromCur}/{toCur}")
    responseJson = response.json()
    lastUpdateTime = datetime.utcfromtimestamp(responseJson["time_last_update_unix"])
    tdelta = datetime.now() - lastUpdateTime
    assert(tdelta.days < 2)
    return responseJson["conversion_rate"]

RATES_CACHE_PATH = "ratesCache.pickle"
# Also cache in memory, so that the file is only read once
@memo
def getOrRetrieveLatestRates() -> RetrivedRates:
    rates: Optional[RetrivedRates] = None
    if os.path.exists(RATES_CACHE_PATH):
        with open(RATES_CACHE_PATH, "rb") as f:
            rates = pickle.load(f)
    now = datetime.now()
    today = Date(year=now.year, month=now.month, day=now.day)
    targetDay = today if now.hour > 4 else today - timedelta(days=1)
    if rates is not None and rates.dateOfRetrieval == targetDay:
        return rates
    stockConfig = forceReadUserConfig().stock
    assert(stockConfig is not None)
    stockPrice = yfinance.Ticker(stockConfig.stockUnitTick).history(period="1d")["Close"].iloc[-1]
    rates = RetrivedRates(
        JPYCNYRate=currencyRate(JPY, CNY),
        USDJPYRate=currencyRate(USD, JPY),
        USDPerStockUnitShare=cast(float, stockPrice),
        dateOfRetrieval=targetDay)
    with open(RATES_CACHE_PATH, "wb") as f:
        pickle.dump(rates, f)
    return rates


