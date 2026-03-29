from ..process import GroupedProcess, breakpointProcess, moveSalaryToFirstOfDay, sortByDateAndMore
from ..base import *
import transactflow.processes.importer
import transactflow.processes.simple
import transactflow.processes.complex
import transactflow.processes.tax
import transactflow.processes.capitalGain
import transactflow.processes.forecast
from typing import List

def allCombined(includeTaxProcesses: bool) -> GroupedProcess:
    return GroupedProcess(label="All processes", processes=[
        transactflow.processes.importer.process,
        transactflow.processes.simple.process,
        transactflow.processes.complex.process,
        transactflow.processes.capitalGain.process,
        transactflow.processes.forecast.process,
    ] + (
        [transactflow.processes.tax.process] if includeTaxProcesses else []
    ) + [
        sortByDateAndMore,
        moveSalaryToFirstOfDay
    ])

def run(includeTaxProcesses: bool = True, progress = True) -> List[Transaction]:
    return allCombined(includeTaxProcesses=includeTaxProcesses)([], progress=progress)

def runImporterOnly() -> List[Transaction]:
    return transactflow.processes.importer.process([])

def runImporterAndSimple() -> List[Transaction]:
    process = GroupedProcess(label="All transactions", processes=[
        transactflow.processes.importer.process,
        transactflow.processes.simple.process
    ])
    return process([])
