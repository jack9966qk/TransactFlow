from pathlib import Path

from transactflow.base import *
from .helpers import assertFilesContentEqual, writeTransactionsWithStat
from transactflow.processes.runAll import run

def checkAgainstGolden(outputDir: Path):
    goldenOutputPath = outputDir / "golden"
    newOutputPath = outputDir / "new"
    trans = run()
    writeTransactionsWithStat(trans, newOutputPath, pretty=True)
    assertFilesContentEqual(goldenOutputPath, newOutputPath)
