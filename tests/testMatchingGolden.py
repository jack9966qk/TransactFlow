from transactflow.base import *
from tests.helpers import assertFilesContentEqual, writeTransactionsWithStat
from transactflow.processes.runAll import run

OUTPUT_DIR = "test/goldenOutput"
GOLDEN_OUTPUT_PATH = f"{OUTPUT_DIR}/golden"
NEW_OUTPUT_PATH = f"{OUTPUT_DIR}/new"

trans = run()
writeTransactionsWithStat(trans, NEW_OUTPUT_PATH, pretty=True)
assertFilesContentEqual(GOLDEN_OUTPUT_PATH, NEW_OUTPUT_PATH)