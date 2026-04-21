from pathlib import Path

from .common import writeLocalTimeString
from .config import SmbcCardRetrievalConfig


def moveFileForMonthIntoDataDir(filePath: Path, name: str, config: SmbcCardRetrievalConfig):
    moveToPath = config.monthsDir / f"{name}.csv"
    if moveToPath.exists():
        moveToPath.unlink()
    filePath.rename(moveToPath)
    writeLocalTimeString(config.timestampPath)
