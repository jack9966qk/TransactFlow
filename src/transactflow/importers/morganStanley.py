from ..rates import getOrRetrieveLatestRates
from typing import Dict, Iterator, List, TextIO, cast, Optional
from ..base import *
from ..importers.importer import CsvImporter, readCsvWithRawAndLineNum
from dateutil.parser import parse as parseDate
from dataclasses import dataclass
from ..userConfig import forceReadUserConfig

@dataclass
class VestedEquityItem:
    grantDate: Date
    vestingDate: Date
    numUnits: float
    grant: str
    vestedUSDPerShare: float
    vestedUSDJPYRate: float

    @classmethod
    def fromCsvRow(cls, row: Dict[str, str]) -> "VestedEquityItem":
        def usdJpyRate():
            def usdJpyRateFor(date: str):
                # Needs new estimation.
                assert(False)    
            rateStr = row["FX Rate"]
            if rateStr != "": return float(rateStr)
            return usdJpyRateFor(row["Vesting Date"])
        return VestedEquityItem(
            grantDate=parseDate(row["Award Date"]).date(),
            vestingDate=parseDate(row["Vesting Date"]).date(),
            numUnits=float(row[forceReadUserConfig().morganStanleyCsvHeaderNumUnits]),
            grant=row["Award Number"],
            vestedUSDPerShare=float(row["Fair Market Value"].lstrip("$")),
            vestedUSDJPYRate=usdJpyRate())


@dataclass
class UnvestedEquityItem:
    grantDate: Date
    vestingDate: Date
    numUnits: float
    grant: str

    @classmethod
    def fromCsvRow(cls, row: Dict[str, str]) -> "UnvestedEquityItem":
        return UnvestedEquityItem(
            grantDate=parseDate(row["Grant Date"]).date(),
            vestingDate=parseDate(row["Vesting Date"]).date(),
            numUnits=float(row["Total Quantity"]),
            grant=row["Employee Grant Number"])

@dataclass
class WithdrawItem:
    date: Date
    usdPerShare: float
    numUnits: float
    netUSDAmount: float

    @classmethod
    def fromCsvRow(cls, row: Dict[str, str]) -> "WithdrawItem":
        return WithdrawItem(
            date=parseDate(row["Execution Date"]).date(),
            usdPerShare=float(row["Price"].replace(",", "").strip("$")),
            numUnits=abs(float(row["Quantity"].replace(",", ""))),
            netUSDAmount=float(row["Net Amount"].replace(",", "").strip("$")))

def parseVested(statementFilePath: str) -> List[Transaction]:
    def skipStatementLine(raw: str) -> bool:
        return forceReadUserConfig().morganStanleyUnvestedParsingShouldIgnore({}, raw, 0)
    def parseVestedLine(row: dict, raw: str, lineNum: int) -> Optional[Transaction]:
        if forceReadUserConfig().morganStanleyUnvestedParsingShouldIgnore(row, raw, lineNum):
            return None
        item = VestedEquityItem.fromCsvRow(row)
        description = f"Equity {item.numUnits} Units"
        return Transaction(
            date=item.vestingDate,
            description=description,
            rawAmount=MoneyAmount(STOCK_UNIT, item.numUnits),
            account=MORGAN_STANLEY,
            category=EQUITY_VESTING,
            originalFormat=raw,
            relatedTo=EMPLOYER,
            sourceLocation=(statementFilePath, -lineNum),
            referencedExchangeRates=ExchangeRates(
                USDPerStockUnitShare=item.vestedUSDPerShare,
                USDJPYRate=item.vestedUSDJPYRate
            )
        )
    with open(statementFilePath, "r") as f:
        importer = CsvImporter(parseVestedLine, dictReader=True, dropWhile=skipStatementLine)
        return importer.parseFile(cast(TextIO, f))

def parseUnvested(unvestedFilePath: str) -> List[Transaction]:
    def skipUnvestedLine(raw: str) -> bool:
        return forceReadUserConfig().morganStanleyUnvestedParsingShouldIgnore({}, raw, 0)
    def parseUnvestedLine(row: dict, raw: str, lineNum: int) -> Optional[Transaction]:
        if raw.startswith('The numbers on this statement reflect'): return None
        item = UnvestedEquityItem.fromCsvRow(row)
        description = f"Unvested equity {item.numUnits} Units"
        return Transaction(
            date=item.vestingDate,
            description=description,
            rawAmount=MoneyAmount(STOCK_UNIT, 0),
            account=MORGAN_STANLEY,
            category=EQUITY_VESTING,
            originalFormat=raw,
            relatedTo=EMPLOYER,
            sourceLocation=(unvestedFilePath, lineNum),
            adjustments=(item.numUnits,),
            isForecast=True)
    with open(unvestedFilePath, "r") as f:
        importer = CsvImporter(parseUnvestedLine, dictReader=True, dropWhile=skipUnvestedLine)
        return importer.parseFile(cast(TextIO, f))

def parseWithdraw(
    withdrawReportFilePath: str,
    usdJpyRateAtDate: Dict[Date, float]
) -> List[Transaction]:
    def skipWithdrawLine(raw: str) -> bool:
        return forceReadUserConfig().morganStanleyWithdrawParsingShouldIgnore({}, raw, 0)
    # TODO: Replace this workaround with an updated CsvImporter that accepts multiple transactions
    # generated per line.
    gains: List[Transaction] = []
    def parseVestedLine(row: dict, raw: str, lineNum: int) -> Optional[Transaction]:
        if forceReadUserConfig().morganStanleyWithdrawParsingShouldIgnore(row, raw, lineNum):
            return None
        item = WithdrawItem.fromCsvRow(row)
        (numUnitsTransformed, usdPerShareTransformed, descriptionSuffix) = (
            forceReadUserConfig().morganStanleyWithdrawTransform(
                item.date.year, item.numUnits, item.usdPerShare
            )
        )
        rates = ExchangeRates(
            USDPerStockUnitShare=usdPerShareTransformed,
            USDJPYRate=usdJpyRateAtDate[item.date]
        )
        gains.append(Transaction(
            date=item.date,
            description=f"Received from sale of {item.numUnits} Units{descriptionSuffix}",
            rawAmount=MoneyAmount(USD, item.netUSDAmount),
            account=MORGAN_STANLEY,
            category=CURRENCY_CONVERSION_RECEIVED,
            originalFormat=raw,
            relatedTo=MORGAN_STANLEY,
            sourceLocation=(withdrawReportFilePath, -lineNum),
            referencedExchangeRates=rates
        ))
        return Transaction(
            date=item.date,
            description=f"Sale of {item.numUnits} Units{descriptionSuffix}",
            rawAmount=-MoneyAmount(STOCK_UNIT, numUnitsTransformed),
            account=MORGAN_STANLEY,
            category=CURRENCY_CONVERSION_SENT,
            originalFormat=raw,
            relatedTo=MORGAN_STANLEY,
            sourceLocation=(withdrawReportFilePath, -lineNum),
            referencedExchangeRates=rates
        )
    with open(withdrawReportFilePath, "r") as f:
        importer = CsvImporter(parseVestedLine, dictReader=True, dropWhile=skipWithdrawLine)
        sales = importer.parseFile(cast(TextIO, f))
    return sales + gains

def readMorganStanleyCsv(statementFilePath: str,
                         unvestedFilePath: str,
                         includeUnvested: bool,
                         withdrawReportFilePath: str,
                         usdJpyRateAtDate: Dict[Date, float]) -> List[Transaction]:
    withoutUnvested = parseVested(statementFilePath) + parseWithdraw(
        withdrawReportFilePath, usdJpyRateAtDate
    )
    if includeUnvested: return withoutUnvested + parseUnvested(unvestedFilePath)
    return withoutUnvested
