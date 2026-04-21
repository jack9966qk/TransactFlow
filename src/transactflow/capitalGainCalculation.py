from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Generator, Iterable, List, Optional, Union

Date = date

DEBUG = False

@dataclass
class Vest:
    priceUSD: float
    rateUSDJPY: float
    numUnits: float

@dataclass
class Sell:
    priceUSD: float
    rateUSDJPY: float
    numUnits: float

@dataclass
class Activity:
    vestOrSell: Union[Vest, Sell]
    canSkip: bool = False
    date: Optional[Date] = None

@dataclass
class RollingAverage:
    priceJPY: float
    numUnits: float

@dataclass
class CapitalGainEntry:
    costAmount: float
    soldAmount: float
    date: Optional[Date] = None
    @property
    def gainAmount(self): return self.soldAmount - self.costAmount

def genCapitalGain(inUSD: bool) -> Generator[Optional[CapitalGainEntry], Activity, None]:
    """
    Returns a generator that yields capital gain results as it receives activities.

    Ref: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1466.htm
    """
    totalCostValue = 0.0
    totalCostNumUnits = 0
    entryToYield = None
    while True:
        activity = yield entryToYield
        assert(activity is not None)
        if DEBUG: print(f"{activity=}")
        entryToYield = None
        vestOrSell = activity.vestOrSell
        match vestOrSell:
            case Vest(priceUSD=priceUSD, rateUSDJPY=rateUSDJPY, numUnits=numUnits):
                totalCostNumUnits += numUnits
                usdAmount = priceUSD * numUnits
                if DEBUG: print(f"{usdAmount=}")
                totalCostValue += usdAmount if inUSD else usdAmount * rateUSDJPY
            case Sell(priceUSD=priceUSD, rateUSDJPY=rateUSDJPY, numUnits=numUnits):
                avgPrice = ceil(totalCostValue / totalCostNumUnits)
                usdAmount = priceUSD * numUnits
                entryToYield = CapitalGainEntry(
                    costAmount=numUnits * avgPrice,
                    soldAmount=usdAmount if inUSD else usdAmount * rateUSDJPY,
                    date=activity.date)
                if DEBUG: print(f"{entryToYield=}")
                totalCostNumUnits -= numUnits
                totalCostValue = totalCostNumUnits * avgPrice
        if DEBUG: print(f"{totalCostNumUnits=}, {totalCostValue=}")

def capitalGain(activities: Iterable[Activity]) -> List[CapitalGainEntry]:
    entries = []
    generator = genCapitalGain(inUSD=False)
    next(generator)
    for activity in activities:
        entry = generator.send(activity)
        if entry: entries.append(entry)
    return entries

def runExample():
    # Example from https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1466.htm
    entries = capitalGain(activities=[
        Activity(vestOrSell=Vest(priceUSD=800, rateUSDJPY=1.0, numUnits=5000)),
        Activity(vestOrSell=Vest(priceUSD=850, rateUSDJPY=1.0, numUnits=2000)),
        Activity(vestOrSell=Sell(priceUSD=900, rateUSDJPY=1.0, numUnits=3000)),
        Activity(vestOrSell=Vest(priceUSD=870, rateUSDJPY=1.0, numUnits=5000)),
        Activity(vestOrSell=Sell(priceUSD=950, rateUSDJPY=1.0, numUnits=6000))
    ])
    print("Captial gain entries:")
    for entry in entries: print(entry)
    # print(f"Total gain is: {sum(e.gainAmount for e in entries)}")
