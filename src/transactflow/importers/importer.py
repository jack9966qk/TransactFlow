from dataclasses import dataclass
from ..base import JPY, SOURCE_CUTOFF, Account, Date, MoneyAmount, Transaction, syntheticTransaction
from typing import Dict, Iterator, List, Callable, Optional, TextIO, Tuple
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
    f: TextIO
    lastLine: str | None
    def __init__(self, f):
        self.f = f
        self.lastLine = None
    def __iter__(self): return self
    def __next__(self):
        self.lastLine = next(self.f).strip()
        return self.lastLine

def wrapFile(file: TextIO, dropWhile: Optional[Callable[[str], bool]]) -> FileWrapper:
    return FileWrapper(file) if not dropWhile else FileWrapper(itertools.dropwhile(dropWhile, file))

def readCsvWithRawAndLineNum(file: TextIO,
                             dropWhile: Optional[Callable[[str], bool]] = None,
                             **kwargs) -> Iterator[Tuple[List[str], str, int]]:
    wrapper = wrapFile(file, dropWhile)
    reader = csv.reader(wrapper, **kwargs)
    for idx, row in enumerate(reader):
        assert wrapper.lastLine is not None
        yield row, wrapper.lastLine, idx + 1

def readDictCsvWithRawAndLineNum(file: TextIO,
                                 dropWhile: Optional[Callable[[str], bool]] = None,
                                 **kwargs) -> Iterator[Tuple[Dict[str, str], str, int]]:
    wrapper = wrapFile(file, dropWhile)
    reader = csv.DictReader(wrapper, **kwargs)
    for idx, row in enumerate(reader):
        assert wrapper.lastLine is not None
        yield row, wrapper.lastLine, idx + 2

class CsvImporter:
    def __init__(self,
                 transactionFromLine: Callable[[List[str], str, int], Optional[Transaction]],
                 dropWhile: Optional[Callable[[str], bool]] = None,
                 **kwargs):
        self.transactionFromLine = transactionFromLine
        self.dropWhile = dropWhile
        self.readerArgs = kwargs
    def parseFile(self, file: TextIO) -> List[Transaction]:
        reader = readCsvWithRawAndLineNum(file,
                                          dropWhile=self.dropWhile,
                                          **self.readerArgs)
        return [ t for ro, ra, ln in reader if
                (t:= self.transactionFromLine(ro, ra, ln)) is not None]

class DictCsvImporter:
    def __init__(self,
                 transactionFromLine: Callable[[Dict[str, str], str, int], Optional[Transaction]],
                 dropWhile: Optional[Callable[[str], bool]] = None,
                 **kwargs):
        self.transactionFromLine = transactionFromLine
        self.dropWhile = dropWhile
        self.readerArgs = kwargs
    def parseFile(self, file: TextIO) -> List[Transaction]:
        reader = readDictCsvWithRawAndLineNum(file,
                                              dropWhile=self.dropWhile,
                                              **self.readerArgs)
        return [ t for ro, ra, ln in reader if
                (t:= self.transactionFromLine(ro, ra, ln)) is not None]
