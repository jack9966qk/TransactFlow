from ..process import GroupedProcess, Process, moveSalaryToFirstOfDay, sortByDateAndMore
from ..base import *
from ..userConfig import forceReadUserConfig
from .importer import makeProcess as makeImporterProcess
from .capitalGain import addCaptialGainProcess
from .forecast import makeProcess as makeForecastProcess
from typing import List, Optional

def _optionalProcess(proc: Optional["Process"]) -> List["Process"]:
    return [proc] if proc is not None else []

def allCombined(includeTaxProcesses: bool) -> GroupedProcess:
    config = forceReadUserConfig()
    return GroupedProcess(label="All processes", processes=[
        makeImporterProcess(),
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
        makeForecastProcess(),
        *_optionalProcess(
            mapOptional(
                config.processes,
                lambda c: c.taxProcess if includeTaxProcesses else None),
        ),
        sortByDateAndMore,
        moveSalaryToFirstOfDay
    ])

def run(includeTaxProcesses: bool = True, progress = True) -> List[Transaction]:
    return allCombined(includeTaxProcesses=includeTaxProcesses)([], progress=progress)

