from test.helpers import assertFilesContentEqual
from base import *
from retrieval.prestia import mergePrestiaFiles
from updateData import combineSMBCCreditMonthsData
from retrieval.common import InconsistentLinesError, CannotFindAlignmentError
import os

TEST_DATA_DIR = "test/merging_data"

def testSMBCCreditCombine():
    testDir = os.path.join(TEST_DATA_DIR, "smbc-card")
    outputFilePath = os.path.join(TEST_DATA_DIR, "smbc-card-testOutput.csv")
    if os.path.exists(outputFilePath):
        os.remove(outputFilePath)
    for testCase in os.listdir(testDir):
        testCaseDir = os.path.join(testDir, testCase)
        if not os.path.isdir(testCaseDir):
            continue
        print(f"testing {testCase}")
        combineSMBCCreditMonthsData(testCaseDir, outputFilePath)
        expectedFilePath = os.path.join(testCaseDir, "expected.csv")
        assertFilesContentEqual(expectedFilePath, outputFilePath)
    if os.path.exists(outputFilePath):
        os.remove(outputFilePath)

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