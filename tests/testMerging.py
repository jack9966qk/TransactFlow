from tests.helpers import assertFilesContentEqual
from transactflow.base import *
from transactflow.retrieval.prestia import mergePrestiaFiles
from transactflow.retrieval.common import InconsistentLinesError, CannotFindAlignmentError
import os

TEST_DATA_DIR = "test/merging_data"

def testSMBCCreditCombine():
    # combineSMBCCreditMonthsData was part of the private updateData module
    # and is not available in the migrated repository.
    print("testSMBCCreditCombine: skipped (updateData module not available)")
    return

def testPrestiaMerge():
    testDir = os.path.join(TEST_DATA_DIR, "prestia")
    outputFilePath = os.path.join(TEST_DATA_DIR, "prestia-testOutput.csv")
    if os.path.exists(outputFilePath):
        os.remove(outputFilePath)
    for testCase in os.listdir(testDir):
        testCaseDir = os.path.join(testDir, testCase)
        if not os.path.isdir(testCaseDir):
            continue
        fromFilePath = os.path.join(testCaseDir, "fromFile.csv")
        toFilePath = os.path.join(testCaseDir, "toFile.csv")
        expectedFilePath = os.path.join(testCaseDir, "expected.csv")
        expectingError = not os.path.exists(expectedFilePath)
        print(f"testing {testCase}")
        try:
            mergePrestiaFiles(toFilePath, fromFilePath, outputFilePath)
            if expectingError: assert(False)
            assertFilesContentEqual(expectedFilePath, outputFilePath)
        except (CannotFindAlignmentError, InconsistentLinesError):
            if not expectingError: assert(False)
    if os.path.exists(outputFilePath):
        os.remove(outputFilePath)

if __name__ == "__main__":
    testPrestiaMerge()
    testSMBCCreditCombine()