from calendar import c
import os
from ..base import AMEX_JP, EXPENSE, INCOME, JPY, SOURCE_CUTOFF, MoneyAmount, Transaction, synthesizedTransaction
from .importer import CsvImporter, addingCutoffTransactionTo, readDateOfTimestampFile
from dateutil.parser import parse as parseDate
from typing import List, Optional, TextIO, cast

from ..retrieval.amexJp import AMEX_DATA_CONVERTED_DIR, AMEX_DATA_TIMESTAMP_PATH
from ..retrieval.common import forEachFileToReadFrom

def readAmexJpCsvFiles() -> List[List[Transaction]]:
    transactionGroups: List[List[Transaction]] = []
    readFromDir = AMEX_DATA_CONVERTED_DIR
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
            date=readDateOfTimestampFile(AMEX_DATA_TIMESTAMP_PATH),
            account=AMEX_JP)
    )
    return transactionGroups

def readAmexJpCsv(filename: str) -> List[Transaction]:
    with open(filename, "r", encoding="utf-8") as f:
        numLines = len(f.readlines())
    def parseLine(row: List[str], raw: str, lineNum: int) -> Optional[Transaction]:
        nonTransactionFirstColumn = [
            "ご利用履歴",
            "ご利用金額",
            "お支払い/調整金額",
        ]
        match row:
            case []: return None
            case [first, *_] if first.startswith("#") or first in nonTransactionFirstColumn: return None
            case ["ご利用履歴", _, _, _, *_]: return None
            case ["", _, _, _, *_]: return None
            case [_, "", _, _, *_]: return None
            case [_, _, "", _, *_]: return None
            case [_, _, _, "", *_]: return None
            case [da, _, de, am, *extra]:
                cm = None if not len(extra) >= 3 else extra[2]
                if "ご利用日" in da: return None
                amount = -float(am.replace(",", "").replace("￥", ""))
                return Transaction(
                    date=parseDate(da).date(),
                    description=de.encode("utf-8").decode("utf-8"),
                    rawAmount=MoneyAmount(JPY, amount),
                    account=AMEX_JP,
                    category=EXPENSE if amount < 0 else INCOME,
                    originalFormat=raw,
                    sourceLocation=(filename, lineNum - numLines),
                    comment=cm if cm and len(cm) > 0 else None)
            case _:
                assert(False)
    with open(filename, "r", encoding="utf-8") as f:
        importer = CsvImporter(parseLine)
        return importer.parseFile(cast(TextIO, f))
