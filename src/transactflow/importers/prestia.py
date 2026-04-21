from typing import List, Optional

from dateutil.parser import parse as parseDate

from ..base import EXPENSE, INCOME, JPY, SMBC_PRESTIA, MoneyAmount, Transaction
from .importer import CsvImporter, addingCutoffTransactionTo, readDateOfTimestampFile


def readPrestiaCsv(filename: str, timestampPath: str) -> List[Transaction]:
    def readNumOfLines() -> int:
        counter = 0
        with open(filename, "r", encoding="shift_jis") as f:
            for _ in f.readlines(): counter += 1
        return counter
    numLines = readNumOfLines()

    def isValidPrestiaTransaction(line: str) -> bool:
        if line[0] == "#": return False
        return True

    def parsePrestiaLine(row: List[str], raw: str, lineNum: int) -> Optional[Transaction]:
        if not isValidPrestiaTransaction(raw): return None
        da, de, am, _ = row
        amount = float(am.rstrip(" JPY").replace(",", ""))
        categoty = EXPENSE if amount < 0 else INCOME
        return Transaction(
            date=parseDate(da).date(),
            description=de,
            rawAmount=MoneyAmount(JPY, amount),
            account=SMBC_PRESTIA,
            rawRecord=raw,
            category=categoty,
            sourceLocation=(filename, lineNum - numLines - 1))
    
    with open(filename, "r", encoding="shift_jis") as f:
        importer = CsvImporter(parsePrestiaLine)
        transactions = importer.parseFile(f)
    return addingCutoffTransactionTo(
        transactions,
        date=readDateOfTimestampFile(timestampPath),
        account=SMBC_PRESTIA)
