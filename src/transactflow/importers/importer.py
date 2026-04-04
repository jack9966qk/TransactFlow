from dataclasses import dataclass
from ..base import JPY, SOURCE_CUTOFF, Account, Date, MoneyAmount, Transaction, syntheticTransaction
from typing import Any, Dict, Iterator, List, Callable, Optional, TextIO, Tuple, Union
import itertools
import csv
from dateutil.parser import parse as parseDate

from ..process import sortByDateAndMore

def readDateOfTimestampFile(path: str) -> Date:
    with open(path, "r") as f:
        return parseDate(f.read()).date()

def addingCutoffTransactionTo(transactions: List[Transaction], date: Date, account: Account):
    return sortByDateAndMore(transactions + [
        syntheticTransaction(
            date=date,
            description=f"{account} data source cutoff",
            amount=MoneyAmount(JPY, 0),
            category=SOURCE_CUTOFF,
            account=account)
    ])

@dataclass
class RepaymentContext:
    date: Optional[Date] = None
    amount: Optional[MoneyAmount] = None

class FileWrapper:
    def __init__(self, f):
        self.f = f
        self.last_line = None
    def __iter__(self): return self
    def __next__(self):
        self.last_line = next(self.f)
        return self.last_line

def readCsvWithRawAndLineNum(file,
                             dictReader = False,
                             dropWhile = None,
                             **kwargs) -> Iterator[Tuple[Any, str, int]]:
    wrapper = FileWrapper(file) if not dropWhile else FileWrapper(itertools.dropwhile(dropWhile, file))
    reader = csv.DictReader(wrapper, **kwargs) if dictReader \
             else csv.reader(wrapper, **kwargs)
    for idx, row in enumerate(reader):
        lineNum = idx + 2 if dictReader else idx + 1
        yield row, wrapper.last_line.strip(), lineNum

class CsvImporter:
    def __init__(self,
                 transactionFromLine: Callable[[Any, str, int], Optional[Transaction]],
                 dictReader = False,
                 dropWhile = None,
                 **kwargs):
        self.transactionFromLine = transactionFromLine
        self.dictReader = dictReader
        self.dropWhile = dropWhile
        self.readerArgs = kwargs
    def parseFile(self, file: TextIO) -> List[Transaction]:
        reader = readCsvWithRawAndLineNum(file,
                                          dictReader=self.dictReader,
                                          dropWhile=self.dropWhile,
                                          **self.readerArgs)
        return [ t for ro, ra, ln in reader if
                (t:= self.transactionFromLine(ro, ra, ln)) is not None]