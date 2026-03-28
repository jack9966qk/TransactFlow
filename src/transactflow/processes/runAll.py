from process import GroupedProcess, breakpointProcess, moveSalaryToFirstOfDay, sortByDateAndMore
from base import *
import processes.importer
import processes.simple
import processes.complex
import processes.tax
import processes.capitalGain
import processes.forecast
from typing import List

def allCombined(includeTaxProcesses: bool) -> GroupedProcess:
    return GroupedProcess(label="All processes", processes=[
        processes.importer.process,
        processes.simple.process,
        processes.complex.process,
        processes.capitalGain.process,
        processes.forecast.process,
    ] + (
        processes.tax.processes if includeTaxProcesses else []
    ) + [
        sortByDateAndMore,
        moveSalaryToFirstOfDay
    ])

def run(includeTaxProcesses: bool = True, progress = True) -> List[Transaction]:
    return allCombined(includeTaxProcesses=includeTaxProcesses)([], progress=progress)

def runImporterOnly() -> List[Transaction]:
    return processes.importer.process([])

def runImporterAndSimple() -> List[Transaction]:
    process = GroupedProcess(label="All transactions", processes=[
        processes.importer.process,
        processes.simple.process
    ])
    return process([])
