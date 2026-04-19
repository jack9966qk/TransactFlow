from dataclasses import dataclass
from ..base import EXPENSE, INCOME, JPY, SOURCE_CUTOFF, Account, Currency, Date, MoneyAmount, Transaction, syntheticTransaction
from typing import Dict, Iterator, List, Callable, Optional, TextIO, Tuple
import itertools
import csv
import re
from lxml import etree as ET  # type: ignore[import-untyped]
from pathlib import Path
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

class OfxImporter:
    def __init__(self,
                 financialOrgName: str,
                 account: Account,
                 currency: Currency):
        self.financialOrgName = financialOrgName
        self.account = account
        self.currency = currency

    def parseFile(self, filePath: Path) -> List[Transaction]:
        content = filePath.read_text()
        idx = content.find("<OFX>")
        assert idx >= 0, "Could not find <OFX> element in OFX file"
        xmlContent = re.sub(
            r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", content[idx:])
        xmlContent = re.sub(
            r"<([A-Z][A-Z0-9]*)>([^<\n]+?)(?=<|\n)(?!</\1>)", r"<\1>\2</\1>", xmlContent)
        root = ET.fromstring(xmlContent.encode("utf-8"), ET.XMLParser(recover=True))
        assert root is not None, "lxml recover failed to produce a root element"

        def assertAndGetChildText(parent: ET._Element, tag: str) -> str:
            el = parent.find(tag)
            assert el is not None, f"Missing OFX element: {tag}"
            assert el.text is not None, f"Empty OFX element: {tag}"
            return el.text

        orgText = assertAndGetChildText(root, "SIGNONMSGSRSV1/SONRS/FI/ORG")
        def normalizeSpacing(s: str) -> str:
            return " ".join(s.split())
        assert normalizeSpacing(orgText) == normalizeSpacing(self.financialOrgName), \
            f"Unexpected OFX financial org: {orgText!r}, expected {self.financialOrgName!r}"

        stmtrsList = root.findall("BANKMSGSRSV1/STMTTRNRS/STMTRS")
        assert len(stmtrsList) == 1, f"Expected exactly 1 STMTRS node, got {len(stmtrsList)}"
        stmtrs = stmtrsList[0]

        stmttrns = stmtrs.findall("BANKTRANLIST/STMTTRN")
        stmttrnLineNums: List[int] = []
        searchStart = 0
        for _ in stmttrns:
            pos = content.find("<STMTTRN>", searchStart)
            assert pos >= 0, "Could not locate <STMTTRN> in OFX source text"
            stmttrnLineNums.append(content.count("\n", 0, pos) + 1)
            searchStart = pos + len("<STMTTRN>")

        def makeTransaction(stmttrn: ET._Element, lineNum: int) -> Transaction:
            amount = float(assertAndGetChildText(stmttrn, "TRNAMT"))
            name = assertAndGetChildText(stmttrn, "NAME")
            def optionalOfxChildText(parent: ET._Element, tag: str) -> Optional[str]:
                el = parent.find(tag)
                if el is None: return None
                return el.text
            memo = optionalOfxChildText(stmttrn, "MEMO")
            raw = ET.tostring(stmttrn, encoding="unicode").strip()
            dateStr = assertAndGetChildText(stmttrn, "DTPOSTED")
            assert re.fullmatch(
                r"\d{8}(\d{6}(\.\d+)?)?(\[[+-]?\d+(\.\d+)?(:[A-Z]+)?\])?", dateStr
            ), f"Unexpected OFX date format: {dateStr!r}"
            date = Date(year=int(dateStr[0:4]), month=int(dateStr[4:6]), day=int(dateStr[6:8]))
            sourceLocation = (str(filePath), lineNum)
            return Transaction(
                date=date,
                description=name,
                rawAmount=MoneyAmount(self.currency, amount),
                account=self.account,
                rawRecord=raw,
                sourceLocation=sourceLocation,
                category=EXPENSE if amount < 0 else INCOME,
                comment=memo if memo else None)

        return [makeTransaction(e, ln) for e, ln in zip(stmttrns, stmttrnLineNums)]
