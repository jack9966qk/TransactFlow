from typing import Dict, List, Optional, TextIO, cast

from dateutil.parser import parse as parseDate

from ..base import (
    EXPENSE,
    INCOME,
    JPY,
    REVOLUT,
    UNPAIRED_INTERNAL_TRANSFER,
    MoneyAmount,
    Transaction,
)
from .importer import (
    DictCsvImporter,
    addingCutoffTransactionTo,
    readDateOfTimestampFile,
)


def readRevolutCsv(filename: str, timestampPath: str) -> List[Transaction]:
    def parseRevolutLine(row: Dict[str, str], raw: str, lineNum: int) -> Optional[Transaction]:
        amount = float(row["Amount"])
        date = parseDate(row["Started Date"]).date()
        def category():
            if row["Type"] == "TOPUP": return UNPAIRED_INTERNAL_TRANSFER
            return EXPENSE if amount < 0 else INCOME
        assert(row["Currency"] == "JPY")
        return Transaction(
            date=date,
            description=row["Description"],
            rawAmount=MoneyAmount(JPY, amount),
            account=REVOLUT,
            category=category(),
            rawRecord=raw,
            sourceLocation=(filename, lineNum))

    with open(filename, "r", encoding="utf-8") as f:
        importer = DictCsvImporter(parseRevolutLine)
        transactions = importer.parseFile(cast(TextIO, f))
    return addingCutoffTransactionTo(
        transactions,
        date=readDateOfTimestampFile(timestampPath),
        account=REVOLUT)
