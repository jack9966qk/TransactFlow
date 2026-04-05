from typing import Dict, List, TextIO, cast, Optional
from ..base import *
from ..importers.importer import CsvImporter
from dateutil.parser import parse as parseDate
from dataclasses import dataclass
from ..userConfig import MorganStanleyImportConfig

@dataclass
class VestedEquityItem:
    grantDate: Date
    vestingDate: Date
    numUnits: float
    grant: str
    vestedUSDPerShare: float
    vestedUSDJPYRate: float

    @classmethod
    def fromCsvRow(
        cls, row: Dict[str, str], usdJpyRateAtDate: Dict[Date, float],
        config: MorganStanleyImportConfig
    ) -> "VestedEquityItem":
        def usdJpyRate():
            rateStr = row["FX Rate"]
            if rateStr != "": return float(rateStr)
            return usdJpyRateAtDate[parseDate(row["Vesting Date"]).date()]
        return VestedEquityItem(
            grantDate=parseDate(row["Award Date"]).date(),
            vestingDate=parseDate(row["Vesting Date"]).date(),
            numUnits=float(row[config.csvHeaderNumUnits]),
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

def parseVested(
    config: MorganStanleyImportConfig,
) -> List[Transaction]:
    statementFilePath = config.equityStatementPath
    def skipStatementLine(raw: str) -> bool:
        return config.vestedParsingShouldIgnore({}, raw, 0)
    def parseVestedLine(row: dict, raw: str, lineNum: int) -> Optional[Transaction]:
        if config.vestedParsingShouldIgnore(row, raw, lineNum):
            return None
        item = VestedEquityItem.fromCsvRow(row, config.usdJpyRateAtDate, config)
        description = f"Equity {item.numUnits} Stock Units"
        return Transaction(
            date=item.vestingDate,
            description=description,
            rawAmount=MoneyAmount(config.stockUnit, item.numUnits),
            account=MORGAN_STANLEY,
            category=EQUITY_VESTING,
            rawRecord=raw,
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

def parseUnvested(
    config: MorganStanleyImportConfig,
) -> List[Transaction]:
    unvestedFilePath = config.equityUnvestedPath
    def skipUnvestedLine(raw: str) -> bool:
        return config.unvestedParsingShouldIgnore({}, raw, 0)
    def parseUnvestedLine(row: dict, raw: str, lineNum: int) -> Optional[Transaction]:
        if raw.startswith('The numbers on this statement reflect'): return None
        item = UnvestedEquityItem.fromCsvRow(row)
        description = f"Unvested equity {item.numUnits} Stock Units"
        return Transaction(
            date=item.vestingDate,
            description=description,
            rawAmount=MoneyAmount(config.stockUnit, 0),
            account=MORGAN_STANLEY,
            category=EQUITY_VESTING,
            rawRecord=raw,
            relatedTo=EMPLOYER,
            sourceLocation=(unvestedFilePath, lineNum),
            adjustments=(item.numUnits,),
            isForecast=True)
    with open(unvestedFilePath, "r") as f:
        importer = CsvImporter(parseUnvestedLine, dictReader=True, dropWhile=skipUnvestedLine)
        return importer.parseFile(cast(TextIO, f))

def parseWithdraw(
    config: MorganStanleyImportConfig,
) -> List[Transaction]:
    withdrawReportFilePath = config.withdrawPath
    def skipWithdrawLine(raw: str) -> bool:
        return config.withdrawParsingShouldIgnore({}, raw, 0)
    # TODO: Replace this workaround with an updated CsvImporter that accepts multiple transactions
    # generated per line.
    gains: List[Transaction] = []
    def parseWithdrawLine(row: dict, raw: str, lineNum: int) -> Optional[Transaction]:
        if config.withdrawParsingShouldIgnore(row, raw, lineNum):
            return None
        item = WithdrawItem.fromCsvRow(row)
        (numUnitsTransformed, usdPerShareTransformed, descriptionSuffix) = (
            config.withdrawTransform(
                item.date.year, item.numUnits, item.usdPerShare
            )
        )
        rates = ExchangeRates(
            USDPerStockUnitShare=usdPerShareTransformed,
            USDJPYRate=config.usdJpyRateAtDate[item.date]
        )
        gains.append(Transaction(
            date=item.date,
            description=f"Received from sale of {item.numUnits} Stock Units{descriptionSuffix}",
            rawAmount=MoneyAmount(USD, item.netUSDAmount),
            account=MORGAN_STANLEY,
            category=CURRENCY_CONVERSION_RECEIVED,
            rawRecord=raw,
            relatedTo=MORGAN_STANLEY,
            sourceLocation=(withdrawReportFilePath, -lineNum),
            referencedExchangeRates=rates
        ))
        return Transaction(
            date=item.date,
            description=f"Sale of {item.numUnits} Stock Units{descriptionSuffix}",
            rawAmount=-MoneyAmount(config.stockUnit, numUnitsTransformed),
            account=MORGAN_STANLEY,
            category=CURRENCY_CONVERSION_SENT,
            rawRecord=raw,
            relatedTo=MORGAN_STANLEY,
            sourceLocation=(withdrawReportFilePath, -lineNum),
            referencedExchangeRates=rates
        )
    with open(withdrawReportFilePath, "r") as f:
        importer = CsvImporter(parseWithdrawLine, dictReader=True, dropWhile=skipWithdrawLine)
        sales = importer.parseFile(cast(TextIO, f))
    return sales + gains

def readMorganStanleyCsv(config: MorganStanleyImportConfig) -> List[Transaction]:
    withoutUnvested = parseVested(config) + parseWithdraw(config)
    return withoutUnvested + parseUnvested(config)
