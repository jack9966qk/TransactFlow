from calendar import c
from datetime import timedelta
import os
from base import DINERS_CLUB, EMPTY_AMOUNT, EXPECTED_INTERNAL_TRANSFER, EXPENSE, INCOME, JPY, SMBC_CREDIT_CARD, SOURCE_CUTOFF, Date, MoneyAmount, Transaction, synthesizedTransaction
from retrieval.common import forEachFileToReadFrom
from retrieval.diners import DINERS_DATA_MONTHS_DIR, DINERS_DATA_TIMESTAMP_PATH
from importers.importer import CsvImporter, RepaymentContext, addingCutoffTransactionTo, readDateOfTimestampFile
from dateutil.parser import parse as parseDate
from typing import List, Optional, TextIO, cast, Tuple

def readDinersCsvFiles() -> List[List[Transaction]]:
    transactionGroups: List[List[Transaction]] = []
    readFromDir = DINERS_DATA_MONTHS_DIR
    def addTransactionsToGroup(fileName: str, incomplete: bool):
        readFromPath = os.path.join(readFromDir, fileName)
        transactionGroups.append(readDinersCsv(readFromPath))
    forEachFileToReadFrom(
        dir=DINERS_DATA_MONTHS_DIR,
        isCompleteSection=lambda name: len(name) == 6 and name.isdigit(),
        # TODO: maybe find some way to get incomplete month data
        isIncompleteSection=lambda name: False,
        sortingKeyFn=lambda name: int(name[:6]),
        id=lambda name: name[:6],
        runFn=addTransactionsToGroup)
    transactionGroups.append(
        addingCutoffTransactionTo(
            [],
            date=readDateOfTimestampFile(DINERS_DATA_TIMESTAMP_PATH),
            account=DINERS_CLUB)
    )
    return transactionGroups

def readDinersCsv(filePath: str) -> List[Transaction]:
    def parseAmount(text: str) -> MoneyAmount:
        return MoneyAmount(JPY, float(text.replace(",", "")))
    repaymentContext = RepaymentContext()
    def parseDinersLine(row: List[str], raw: str, lineNum: int) -> Optional[Transaction]:
        match row:
            case ["\ufeff\"利用者\"", "利用年月日", "明細No", *_]: return None
            case ["", "", "", "当月の請求金額内訳", *_]: return None
            case ["", "", "", "１回払い　　　　　　計", *_]: return None
            case ["", "", "", "合　　　　　　　　　計", "", total,"", "", "", "", "", ""]:
                repaymentContext.amount = parseAmount(total)
                return None
            case ["本会員", da, _, de, typ, am, _, _, _, _, c1, c2]: pass
            case _: assert(False)
        comment = ""
        if typ == "返品":
            amount = MoneyAmount(JPY, 0)
            comment += "(Refund) "
        else:
            amount = -parseAmount(am)
        date = parseDate(da).date()
        category = EXPENSE if amount.quantity < 0 else INCOME
        comment += c1 + c2
        return Transaction(
            date=date,
            description=de,
            rawAmount=amount,
            account=DINERS_CLUB,
            category=category,
            originalFormat=raw,
            sourceLocation=(filePath, lineNum),
            comment=comment if len(comment) > 0 else None)

    with open(filePath, "r", encoding="utf-8") as f:
        importer = CsvImporter(parseDinersLine)
        transactions = importer.parseFile(cast(TextIO, f))

    assert((repaymentAmount := repaymentContext.amount) is not None)
    fileName = os.path.basename(filePath)
    groupYear = int(fileName[:4])
    groupMonth = int(fileName[4:6])
    shouldRollover = (groupMonth == 12)
    repaymentYear = groupYear + 1 if shouldRollover else groupYear
    repaymentMonth = 1 if shouldRollover else groupMonth + 1
    estimatedRepaymentDate = Date(year=repaymentYear, month=repaymentMonth, day=10)
    expectedRepayment = synthesizedTransaction(
        date=estimatedRepaymentDate,
        amount=repaymentAmount,
        account=DINERS_CLUB,
        description="Synthesized expected repayment for Diners Club",
        category=EXPECTED_INTERNAL_TRANSFER,
    )

    return transactions + [expectedRepayment]
