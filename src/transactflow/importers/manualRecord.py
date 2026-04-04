from ..base import *
from ..process import *
from .importer import CsvImporter
from dateutil.parser import parse as parseDate
from typing import List

def readManualRecordCsv(filename: str) -> List[Transaction]:
    def parseLine(row, raw, lineNum) -> Transaction:
        expenseAmount, categoryStr, description, time = row
        category = EXPENSE
        if categoryStr == "Entertainment":
            category = ENTERTAINMENT
        if categoryStr == "Food/Drink":
            category = FOOD_DRINK_OUTSIDE
        amount = -float(expenseAmount)
        date = parseDate(time).date()
        return Transaction(
            date=date,
            description=description,
            rawAmount=MoneyAmount(JPY, amount),
            account=CASH,
            relatedTo=GENERAL_EXPENSE_DESTINATION,
            category=category,
            rawRecord=raw,
            sourceLocation=(filename, lineNum))

    with open(filename, "r") as f:
        importer = CsvImporter(parseLine)
        return importer.parseFile(f)
