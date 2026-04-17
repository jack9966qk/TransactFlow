from pathlib import Path

from .common import prependWithAlignment, shiftCombinedForNewMerge, writeLocalTimeString
from .config import SuicaRetrievalConfig

def mergeSuicaFiles(combined: Path, newSection: Path, outputPath: Path):
    def canUseAsAlignment(lineWithContext):
        if lineWithContext.lineAfter is None: return False
        dateChange = (lineWithContext.line[:5] !=
                      lineWithContext.lineAfter[:5])
        return dateChange
    prependWithAlignment(newSection, combined, canUseAsAlignment,
                         outFilePath=outputPath, encoding="utf-8")


def updateFilesWithNewOriginalFile(filePath: Path, config: SuicaRetrievalConfig):
    # Move file to data directory
    combined = config.dataDir / "combined.tsv"
    combinedPrev = shiftCombinedForNewMerge(config.dataDir, "tsv")
    if combinedPrev:
        # Merge to combined file
        mergeSuicaFiles(combinedPrev, filePath, combined)
    else:
        filePath.rename(combined)
    writeLocalTimeString(config.timestampPath)
