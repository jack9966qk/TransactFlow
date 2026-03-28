from calendar import c
from dataclasses import dataclass
import os
from ..base import AMEX_JP, EXPECTED_INTERNAL_TRANSFER, JCB_CREDIT_CARD, EXPENSE, INCOME, JPY, SMBC_CREDIT_CARD, SOURCE_CUTOFF, MoneyAmount, Transaction, Date, sumSingleCurrencyAmounts, synthesizedTransaction
from ..retrieval.common import forEachFileToReadFrom
from .importer import CsvImporter, RepaymentContext, addingCutoffTransactionTo, readDateOfTimestampFile
from typing import List, Optional, TextIO, cast, Tuple
from datetime import timedelta
import re

JCB_DATA_MONTHS_DIR = "./data/rawTransactions/jcb/months"
JCB_DATA_TIMESTAMP_PATH = "./data/rawTransactions/jcb/last_update_time"
JCB_EXPECTED_AUTOMATIC_REPAYMENT_DESCRIPTION = "Synthesized expected repayment for JCB"
JCB_EXPECTED_MANUAL_REPAYMENT_DESCRIPTION = "Synthesized expected manual repayment for JCB"

def readJcbCsvFiles() -> List[List[Transaction]]:
    transactionGroups: List[List[Transaction]] = []
    readFromDir = JCB_DATA_MONTHS_DIR
    def addTransactionsToGroup(fileName: str, incomplete: bool):
        readFromPath = os.path.join(readFromDir, fileName)
        transactionGroups.append(readJcbCsv(readFromPath))
    def isIncompleteSection(fileName: str): return "incomplete" in fileName
    forEachFileToReadFrom(
        dir=readFromDir,
        isCompleteSection=lambda name: not isIncompleteSection(name),
        isIncompleteSection=isIncompleteSection,
        sortingKeyFn=lambda name: int(name[:6]),
        id=lambda name: name[:6],
        runFn=addTransactionsToGroup)
    transactionGroups.append(
        addingCutoffTransactionTo(
            [],
            date=readDateOfTimestampFile(JCB_DATA_TIMESTAMP_PATH),
            account=JCB_CREDIT_CARD)
    )
    return transactionGroups

def readJcbCsv(filePath: str) -> List[Transaction]:
    def parseJcbDate(text: str, repaymentContext: RepaymentContext) -> Date:
        """
        Parse date in the JCB CSV format.

        Preferred over other date parsing libraries as some dates have missing days, which is not
        handled well by the libraries.
        """
        if match := re.match(r"\s*(\d\d\d\d)/(\d\d)/(\d\d)", text):
            return Date(
                year=int(match.group(1)),
                month=int(match.group(2)),
                day=int(match.group(3))
            )
        elif match := re.match(r"\s+(\d\d\d\d)/(\d\d)", text):
            # Some transactions do not have a day, for example, card annual fees.
            return Date(
                year=int(match.group(1)),
                month=int(match.group(2)),
                day=1
            )
        elif len(text) == 0:
            # Some transactions do not even have a month, e.g. "２０２５年６月発送コンビニ用紙料".
            repaymentDate = repaymentContext.date
            assert(repaymentDate is not None)
            return repaymentDate - timedelta(days=30)
        assert(False)

    def parseJcbAmount(text: str) -> MoneyAmount:
        quantity = float(text.replace(",", "").replace(" ", ""))
        return MoneyAmount(JPY, quantity)

    repaymentContext = RepaymentContext()
    def parseLine(row: List[str], raw: str, lineNum: int) -> Optional[Transaction]:
        match row:
            case []: return None
            case [first, *_] if first.startswith("#"): return None
            case ["","","今回のお支払日", da]:
                assert(repaymentContext.date is None)
                repaymentContext.date = parseJcbDate(da, repaymentContext)
                return None
            case ["","","今回のお支払金額合計(￥)", am]:
                assert(repaymentContext.amount is None)
                repaymentContext.amount = parseJcbAmount(am)
                return None
            case ["",""," うち国内ご利用金額合計(￥)", _]: return None
            case ["",""," うち海外ご利用金額合計(￥)", _]: return None
            case ["【ご利用明細】"]: return None
            case ["ご利用者","カテゴリ", _, _ , _, _ , _, _, _ , _ , _, _]: return None
            case [_, _, "","お支払済分　ご返金額","","","","",_, _, _, _]:
                # already covered by the line before this one.
                return None
            case [_, _, da, de , am, _, _, c1, amAlt, _, c2, _]:
                if c1 == "取消": assert(amAlt == "")
                # elif amAlt != "": assert(am == amAlt)
                amount = -parseJcbAmount(am) if len(am) > 0 else -parseJcbAmount(amAlt)
                comment = ", ".join([c1, c2])
                return Transaction(
                    date=parseJcbDate(da, repaymentContext),
                    description=de.encode("utf-8").decode("utf-8"),
                    rawAmount=amount,
                    account=JCB_CREDIT_CARD,
                    category=EXPENSE if amount.quantity < 0 else INCOME,
                    originalFormat=raw,
                    sourceLocation=(filePath, lineNum),
                    comment=comment if len(c1 + c2) > 0 else None)
            case _:
                assert(False)
    with open(filePath, "r", encoding="cp932") as f:
        importer = CsvImporter(parseLine)
        transactions = importer.parseFile(cast(TextIO, f))
    assert((repaymentDate := repaymentContext.date) is not None)
    assert((repaymentAmount := repaymentContext.amount) is not None)
    expectedRepayments: List[Transaction] = []
    calculatedTotalAmount = sumSingleCurrencyAmounts(t.adjustedAmount for t in transactions)
    netTotal = calculatedTotalAmount + repaymentAmount
    if netTotal.quantity != 0:
        expectedRepayments.append(synthesizedTransaction(
            date=repaymentDate - timedelta(days=30),
            amount=-netTotal,
            account=JCB_CREDIT_CARD,
            description=JCB_EXPECTED_MANUAL_REPAYMENT_DESCRIPTION,
            category=EXPECTED_INTERNAL_TRANSFER,
        ))
    expectedRepayments.append(synthesizedTransaction(
        date=repaymentDate,
        amount=repaymentAmount,
        account=JCB_CREDIT_CARD,
        description=JCB_EXPECTED_AUTOMATIC_REPAYMENT_DESCRIPTION,
        category=EXPECTED_INTERNAL_TRANSFER,
    ))
    return transactions + expectedRepayments

