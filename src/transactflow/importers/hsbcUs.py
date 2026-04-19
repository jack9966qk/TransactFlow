from pathlib import Path

from transactflow.base import HSBC_US, USD, Transaction
from transactflow.importers.importer import (
    OfxImporter,
    addingCutoffTransactionTo,
    readDateOfTimestampFile,
)

def readHSBCUSOFXFiles(directory: Path, timestampPath: Path) -> list[Transaction]:
    transactions: list[Transaction] = []
    for childPath in directory.iterdir():
        assert childPath.suffix == ".ofx"
        transactions.extend(readHSBCUSOFX(childPath))
    return addingCutoffTransactionTo(
        transactions, date=readDateOfTimestampFile(str(timestampPath)), account=HSBC_US
    )

def readHSBCUSOFX(filePath: Path):
    return OfxImporter(
        financialOrgName="HSBC Bank USA, N.A", account=HSBC_US, currency=USD
    ).parseFile(filePath)
