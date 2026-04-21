from typing import Optional, TextIO, cast

from dateutil.parser import parse as parseDate

from ..base import EXPENSE, INCOME, JPY, SBI_NET_BANK, MoneyAmount, Transaction
from .importer import (
    DictCsvImporter,
    addingCutoffTransactionTo,
    readDateOfTimestampFile,
)


def readSBINetBankCSV(filename: str, timestampPath: str) -> list[Transaction]:
    def readNumOfLines() -> int:
        counter = 0
        with open(filename, "r", encoding="shift_jis") as f:
            for _ in f.readlines(): counter += 1
        return counter
    numLines = readNumOfLines()

    def parseSBITransactionLine(row: dict[str, str], raw: str, lineNum: int) -> Optional[Transaction]:
        def amountQuantity():
            if (expenseAmountString := row["出金金額(円)"]):
                return -float(expenseAmountString.replace(",", ""))
            return float(row["入金金額(円)"].replace(",", ""))
        quantity = amountQuantity()
        return Transaction(
            date=parseDate(row["日付"]).date(),
            description=row["内容"],
            rawAmount=MoneyAmount(JPY, quantity),
            account=SBI_NET_BANK,
            rawRecord=raw,
            category=EXPENSE if quantity < 0 else INCOME,
            sourceLocation=(filename, lineNum - numLines - 1))

    with open(filename, "r", encoding="shift_jis") as f:
        importer = DictCsvImporter(parseSBITransactionLine)
        transactions = importer.parseFile(cast(TextIO, f))
    return addingCutoffTransactionTo(
        transactions,
        date=readDateOfTimestampFile(timestampPath),
        account=SBI_NET_BANK)
