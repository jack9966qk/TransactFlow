import os

from retrieval.common import writeLocalTimeString

SMBC_CREDIT_DATA_DIR = "./data/rawTransactions/smbc-card"
SMBC_CREDIT_DATA_MONTHS_DIR = "./data/rawTransactions/smbc-card/months"
SMBC_CREDIT_DATA_TIMESTAMP_PATH = "./data/rawTransactions/smbc-card/last_update_time"

def moveFileForMonthIntoDataDir(filePath: str, name: str):
    moveToPath = os.path.join(SMBC_CREDIT_DATA_MONTHS_DIR, f"{name}.csv")
    if os.path.exists(moveToPath):
        os.remove(moveToPath)
    os.rename(filePath, moveToPath)
    writeLocalTimeString(SMBC_CREDIT_DATA_TIMESTAMP_PATH)
