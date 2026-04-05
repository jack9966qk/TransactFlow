from ..process import GroupedProcess, Process, moveSalaryToFirstOfDay, sortByDateAndMore
from ..base import *
from ..userConfig import forceReadUserConfig
from .importer import makeProcess as makeImporterProcess
from .capitalGain import process as capitalGainProcess
from .forecast import makeProcess as makeForecastProcess
from typing import List, Optional

def _optionalProcess(proc: Optional["Process"]) -> List["Process"]:
    return [proc] if proc is not None else []

def allCombined(includeTaxProcesses: bool) -> GroupedProcess:
    config = forceReadUserConfig().processes
    return GroupedProcess(label="All processes", processes=[
        makeImporterProcess(),
        *_optionalProcess(config.simpleProcess if config else None),
        *_optionalProcess(config.complexProcess if config else None),
        capitalGainProcess,
        makeForecastProcess(),
    ] + (
        _optionalProcess(config.taxProcess if config else None) if includeTaxProcesses else []
    ) + [
        sortByDateAndMore,
        moveSalaryToFirstOfDay
    ])

def run(includeTaxProcesses: bool = True, progress = True) -> List[Transaction]:
    return allCombined(includeTaxProcesses=includeTaxProcesses)([], progress=progress)

