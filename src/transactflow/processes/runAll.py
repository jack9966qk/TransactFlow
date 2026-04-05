from transactflow.rates import getOrRetrieveLatestRates

from ..process import GroupedProcess, Process, moveSalaryToFirstOfDay, sortByDateAndMore
from ..base import *
from ..userConfig import UserConfig
from .importer import makeProcess as makeImporterProcess
from .capitalGain import addCaptialGainProcess
from .forecast import makeProcess as makeForecastProcess
from typing import List, Optional

def _optionalProcess(proc: Optional["Process"]) -> List["Process"]:
    return [proc] if proc is not None else []

def allCombined(config: UserConfig, includeTaxProcesses: bool) -> GroupedProcess:
    return GroupedProcess(label="All processes", processes=[
        *([] if config.importers is None else [makeImporterProcess(config.importers)]),
        *_optionalProcess(
            mapOptional(config.processes, lambda c: c.simpleProcess),
        ),
        *_optionalProcess(
            mapOptional(config.processes, lambda c: c.complexProcess),
        ),
        *(
            [addCaptialGainProcess(unit) for unit in config.stock.stockUnits]
            if config.stock is not None else []
        ),
        *([] if config.forecast is None else [makeForecastProcess(config.forecast)]),
        *_optionalProcess(
            mapOptional(
                config.processes,
                lambda c: c.taxProcess if includeTaxProcesses else None),
        ),
        sortByDateAndMore,
        moveSalaryToFirstOfDay
    ])

def preloadRatesWithConfig(config: UserConfig):
    stockUnits: frozenset[StockUnit] = frozenset()
    if (stockConfig := config.stock) is not None:
        stockUnits = stockConfig.stockUnits
    _ = getOrRetrieveLatestRates(stockUnits)

def run(config: UserConfig, includeTaxProcesses: bool = True, progress: bool = True) -> List[Transaction]:
    preloadRatesWithConfig(config)
    return allCombined(config, includeTaxProcesses=includeTaxProcesses)([], progress=progress)
