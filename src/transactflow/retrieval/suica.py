from .common import prependWithAlignment, shiftCombinedForNewMerge, writeLocalTimeString
import os

SUICA_DATA_DIR = "./data/rawTransactions/suica"
SUICA_DATA_TIMESTAMP_PATH = "./data/rawTransactions/suica/last_update_time"

def mergeSuicaFiles(combined, newSection, outputPath):
    def canUseAsAlignment(lineWithContext):
        if lineWithContext.lineAfter is None: return False
        dateChange = (lineWithContext.line[:5] !=
                      lineWithContext.lineAfter[:5])
        return dateChange
    prependWithAlignment(newSection, combined, canUseAsAlignment,
                         outFilePath=outputPath, encoding="utf-8")


def updateFilesWithNewOriginalFile(filePath: str):
    # Move file to data directory
    combined = os.path.join(SUICA_DATA_DIR, "combined.tsv")
    combinedPrev = shiftCombinedForNewMerge(SUICA_DATA_DIR, "tsv")
    if combinedPrev:
        # Merge to combined file
        mergeSuicaFiles(combinedPrev, filePath, combined)
    else:
        os.rename(filePath, combined)
    writeLocalTimeString(SUICA_DATA_TIMESTAMP_PATH)
