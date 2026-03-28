from ..base import INTERNAL_TRANSFER, REVOLUT, EXPENSE, INCOME, JPY, SOURCE_CUTOFF, UNPAIRED_INTERNAL_TRANSFER, MoneyAmount, Transaction, synthesizedTransaction
from .importer import CsvImporter, addingCutoffTransactionTo, readDateOfTimestampFile
from dateutil.parser import parse as parseDate
from typing import Dict, List, Optional, TextIO, cast

REVOLUT_DATA_TIMESTAMP_PATH = "./data/rawTransactions/revolut/last_update_time"

def readRevolutCsv(filename: str) -> List[Transaction]:
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
            originalFormat=raw,
            sourceLocation=(filename, lineNum))

    with open(filename, "r", encoding="utf-8") as f:
        importer = CsvImporter(parseRevolutLine, dictReader=True)
        transactions = importer.parseFile(cast(TextIO, f))
    return addingCutoffTransactionTo(
        transactions,
        date=readDateOfTimestampFile(REVOLUT_DATA_TIMESTAMP_PATH),
        account=REVOLUT)
