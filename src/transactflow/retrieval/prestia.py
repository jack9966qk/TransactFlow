from retrieval.common import LineWithContext, prependWithAlignment, shiftCombinedForNewMerge, writeLocalTimeString
import os

PRESTIA_DATA_DIR = "./data/rawTransactions/prestia"
PRESTIA_DATA_TIMESTAMP_PATH = "./data/rawTransactions/prestia/last_update_time"

def mergePrestiaFiles(combined, newSection, outputPath):
    def canUseAsAlignment(lineWithContext: LineWithContext):
        if lineWithContext.lineAfter is None: return False
        dateChange = (lineWithContext.line[:12] !=
                      lineWithContext.lineAfter[:12])
        return dateChange
    prependWithAlignment(newSection, combined, canUseAsAlignment,
                         outFilePath=outputPath)

def updateFilesWithNewOriginalFile(filePath: str):
    # Move file to data directory
    combined = os.path.join(PRESTIA_DATA_DIR, "combined.csv")
    combinedPrev = shiftCombinedForNewMerge(PRESTIA_DATA_DIR, "csv")
    if combinedPrev:
        # Merge to combined file
        mergePrestiaFiles(combinedPrev, filePath, combined)
    else:
        os.rename(filePath, combined)
    writeLocalTimeString(PRESTIA_DATA_TIMESTAMP_PATH)
