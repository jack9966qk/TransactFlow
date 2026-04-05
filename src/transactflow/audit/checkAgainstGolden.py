from pathlib import Path
from typing import Callable

from transactflow.base import *
from transactflow.userConfig import UserConfig
from .helpers import assertFilesContentEqual, writeTransactionsWithStat
from transactflow.processes.runAll import run

def checkAgainstGolden(userConfig: UserConfig, outputDir: Path, transformString: Callable[[str], str]):
    goldenOutputPath = outputDir / "golden"
    newOutputPath = outputDir / "new"
    trans = run(userConfig)
    writeTransactionsWithStat(trans, newOutputPath, transformString, pretty=True)
    assertFilesContentEqual(goldenOutputPath, newOutputPath)
