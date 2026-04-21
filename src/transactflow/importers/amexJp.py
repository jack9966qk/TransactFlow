import os
from typing import Optional, TextIO, cast

from dateutil.parser import parse as parseDate

from ..base import AMEX_JP, EXPENSE, INCOME, JPY, MoneyAmount, Transaction
from ..retrieval.common import forEachFileToReadFrom
from .importer import (
    DictCsvImporter,
    addingCutoffTransactionTo,
    readDateOfTimestampFile,
)


def readAmexJpCsvFiles(convertedDir: str, timestampPath: str) -> list[list[Transaction]]:
    transactionGroups: list[list[Transaction]] = []
    readFromDir = convertedDir
    def addTransactionsToGroup(fileName: str, incomplete: bool):
        readFromPath = os.path.join(readFromDir, fileName)
        transactionGroups.append(readAmexJpCsv(readFromPath))
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
            account=AMEX_JP)
    )
    return transactionGroups

def readAmexJpCsv(filename: str) -> list[Transaction]:
    with open(filename, "r", encoding="utf-8") as f:
        numLines = len(f.readlines())
    def parseLine(row: dict[str, str], raw: str, lineNum: int) -> Optional[Transaction]:
        amount = -float(row["金額"].replace(",", "").replace("￥", ""))
        if "追加情報" in row:
            comment = row["追加情報"]
        else:
            # For some files the header for additional info is missing.
            comment = row[""]
        if len(comment) == 0:
            comment = None
        return Transaction(
            date=parseDate(row["ご利用日"]).date(),
            description=row["ご利用内容"].encode("utf-8").decode("utf-8"),
            rawAmount=MoneyAmount(JPY, amount),
            account=AMEX_JP,
            category=EXPENSE if amount < 0 else INCOME,
            rawRecord=raw,
            sourceLocation=(filename, lineNum - numLines),
            comment=comment)
    with open(filename, "r", encoding="utf-8") as f:
        importer = DictCsvImporter(
            parseLine,
            dropWhile=lambda s: "ご利用日,データ処理日,ご利用内容,金額,海外通貨利用金額,換算レート" not in s)
        return importer.parseFile(cast(TextIO, f))
