import os
from typing import Optional, TextIO, cast

from dateutil.parser import parse as parseDate

from ..base import (
    EXPECTED_INTERNAL_TRANSFER,
    EXPENSE,
    INCOME,
    JPY,
    SMBC_CREDIT_CARD,
    Date,
    MoneyAmount,
    Transaction,
    sumSingleCurrencyAmounts,
    syntheticTransaction,
)
from ..process import matching, takeMatched
from ..retrieval.common import forEachFileToReadFrom
from .importer import CsvImporter, addingCutoffTransactionTo, readDateOfTimestampFile


def readSmbcCardCsvFiles(monthsDir: str, timestampPath: str) -> list[list[Transaction]]:
    transactionGroups: list[list[Transaction]] = []
    readFromDir = monthsDir
    def addTransactionsToGroup(fileName: str, incomplete: bool):
        readFromPath = os.path.join(readFromDir, fileName)
        transactionGroups.append(readSmbcCardCsv(readFromPath))
    forEachFileToReadFrom(
        dir=readFromDir,
        isCompleteSection=lambda name: len(name) == 6 and name.isdigit(),
        isIncompleteSection=lambda name: len(name) == 7 and name.isdigit(),
        sortingKeyFn=lambda name: int(name[:6]),
        id=lambda name: name[:6],
        runFn=addTransactionsToGroup)
    transactionGroups.append(
        addingCutoffTransactionTo(
            [],
            date=readDateOfTimestampFile(timestampPath),
            account=SMBC_CREDIT_CARD)
    )
    return transactionGroups

def readSmbcCardCsv(filePath: str) -> list[Transaction]:
    def parseSmbcCreditLine(row: list[str], raw, lineNum) -> Optional[Transaction]:
        match row:
            case []: return None
            case ["", "", "", "", "", total, last] if last == "" or "合計金額は" in last:
                fileName = os.path.basename(filePath)
                year = int(fileName[:4])
                month = int(fileName[4:6])
                return syntheticTransaction(
                    date=Date(year, month, 10),
                    description="Expected repayment with estimated date",
                    amount=MoneyAmount(JPY, float(total)),
                    category=EXPECTED_INTERNAL_TRANSFER,
                    account=SMBC_CREDIT_CARD)
            case [first, *_] if "様" in first: return None
            case [first, *_] if first.startswith("#"): return None
            case [da, de, _, _, _, am, _]: pass
            case [da, de, _, _, _, _, am, _, _, _, _, _, _]: pass
            case _: assert(False)
        amount = -float(am)
        date = parseDate(da).date()
        category = EXPENSE if amount < 0 else INCOME
        return Transaction(
            date=date,
            description=de,
            rawAmount=MoneyAmount(JPY, amount),
            account=SMBC_CREDIT_CARD,
            category=category,
            rawRecord=raw,
            sourceLocation=(filePath, lineNum))

    # Files are readable with "shift_jis" encoding, but it seems like
    # they are actually in "cp932". In "shift_jis", "－" becomes "−"
    # in Python strings and UTF-8 output (although they becomes "－"
    # again when writing to "shift_jis" files). In "cp932", it is always
    # "－".
    # See also: https://qiita.com/yoshi389111/items/9060c8b62df7cac31de9
    # (the section with U+ff0d : FULLWIDTH HYPHEN-MINUS "－")
    with open(filePath, "r", encoding="cp932") as f:
        importer = CsvImporter(parseSmbcCreditLine)
        transactions = importer.parseFile(cast(TextIO, f))
    expectedRepayments, remaining = takeMatched(
        transactions, matching(exactCategory=EXPECTED_INTERNAL_TRANSFER))
    assert(len(expectedRepayments) == 1)
    assert(sumSingleCurrencyAmounts(r.adjustedAmount for r in remaining)
           == -expectedRepayments[0].adjustedAmount)
    return transactions
