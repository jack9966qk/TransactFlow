from pathlib import Path

from .common import LineWithContext, prependWithAlignment, shiftCombinedForNewMerge, writeLocalTimeString
from .config import PrestiaRetrievalConfig

def mergePrestiaFiles(combined: Path, newSection: Path, outputPath: Path):
    def canUseAsAlignment(lineWithContext: LineWithContext):
        if lineWithContext.lineAfter is None: return False
        dateChange = (lineWithContext.line[:12] !=
                      lineWithContext.lineAfter[:12])
        return dateChange
    prependWithAlignment(newSection, combined, canUseAsAlignment,
                         outFilePath=outputPath)

def updateFilesWithNewOriginalFile(filePath: Path, config: PrestiaRetrievalConfig):
    # Move file to data directory
    combined = config.dataDir / "combined.csv"
    combinedPrev = shiftCombinedForNewMerge(config.dataDir, "csv")
    if combinedPrev:
        # Merge to combined file
        mergePrestiaFiles(combinedPrev, filePath, combined)
    else:
        filePath.rename(combined)
    writeLocalTimeString(config.timestampPath)
