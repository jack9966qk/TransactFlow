import os
from typing import Dict, List, Optional, TextIO, cast

from dateutil.parser import parse as parseDate

from ..base import AMEX_US, EXPENSE, INCOME, USD, MoneyAmount, Transaction
from ..retrieval.common import forEachFileToReadFrom
from .importer import (
    DictCsvImporter,
    addingCutoffTransactionTo,
    readDateOfTimestampFile,
)


def readAmexUsCsvFiles(convertedDir: str, timestampPath: str) -> List[List[Transaction]]:
    transactionGroups: List[List[Transaction]] = []
    readFromDir = convertedDir
    def addTransactionsToGroup(fileName: str, incomplete: bool):
        readFromPath = os.path.join(readFromDir, fileName)
        transactionGroups.append(readAmexUsCsv(readFromPath))
    def isCompleteSection(filename: str): return not "incomplete" in filename
    forEachFileToReadFrom(
        dir=readFromDir,
        isCompleteSection=isCompleteSection,
        isIncompleteSection=lambda name: not isCompleteSection(name),
        sortingKeyFn=lambda name: -int(name[:4]),
        id=lambda name: name[:4],
        runFn=addTransactionsToGroup)
    transactionGroups.append(
        addingCutoffTransactionTo(
            [],
            date=readDateOfTimestampFile(timestampPath),
            account=AMEX_US)
    )
    return transactionGroups

def readAmexUsCsv(filename: str) -> List[Transaction]:
    with open(filename, "r", encoding="utf-8") as f:
        numLines = len(f.readlines())
    def parseLine(row: Dict[str, str], raw: str, lineNum: int) -> Optional[Transaction]:
        amount = -float(row["Amount"].replace(",", ""))
        return Transaction(
            date=parseDate(row["Date"]).date(),
            description=row["Description"].encode("utf-8").decode("utf-8"),
            rawAmount=MoneyAmount(USD, amount),
            account=AMEX_US,
            category=EXPENSE if amount < 0 else INCOME,
            rawRecord=raw,
            sourceLocation=(filename, lineNum - numLines),
            comment=None)
    with open(filename, "r", encoding="utf-8") as f:
        headerSubstring = "Date,Description,Amount,Extended Details,Appears On Your Statement As,Address,City/State,Zip Code,Country,Reference,Category"
        importer = DictCsvImporter(
            parseLine,
            dropWhile=lambda s: headerSubstring not in s)
        return importer.parseFile(cast(TextIO, f))
