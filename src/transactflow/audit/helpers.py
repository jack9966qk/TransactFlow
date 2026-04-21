import subprocess
from collections import Counter
from dataclasses import fields
from itertools import zip_longest
from pathlib import Path
from typing import Callable, Generator, List, Optional

from transactflow.analysis import (
    accountBalanceByAccount,
    netWorth,
    totalAccountBalance,
    totalSaving,
)
from transactflow.base import *
from transactflow.multiCurrency import totalAdjustedAmountAsJPY


def filesContentEqual(path1, path2, encoding="utf-8"):
    with open(path1, "r", encoding=encoding) as f1:
        with open(path2, "r", encoding=encoding) as f2:
            for l1, l2 in zip_longest(f1, f2):
                if l1 is None or l2 is None: return False
                if l1 != l2: return False
    return True

def assertFilesContentEqual(path1: Path, path2: Path):
    if not filesContentEqual(path1, path2):
        print(f"Files {path1} and {path2} do not match")
        subprocess.run(["code", "--diff", path1, path2])
        assert(False)

def transactionRepr(t: Transaction, pretty: bool) -> str:
    if not pretty: return repr(t)
    lines = ["Transaction"]
    for field in fields(t):
        def valueRepr() -> Optional[str]:
            value = getattr(t, field.name)
            match (field.name, value):
                case ("isUnrealized", False): return None
                case ("isForecast", False): return None
                case ("relatedTo", None): return None
                case ("comment", None): return None
                case ("referencedExchangeRates", _) if t.referencedExchangeRates.isEmpty:
                    return None
                case ("adjustments", ()): return None
                case ("adjustments", _):
                    formattedQuantities = ", ".join(formatQuantity(q) for q in t.adjustments)
                    return f"({formattedQuantities})"
                # case ("sourceLocation", _):
                #     return "omitted"
                case ("rawAmount", MoneyAmount()):
                    return str(value)
                case ("referencedExchangeRates", _):
                    # if t.date > Date.today():
                    #     return "today's values (omitted)"
                    return str(value)
            return repr(value)
        if (resolvedValueRepr := valueRepr()) is not None:
            lines.append(f"\t{field.name}: {resolvedValueRepr}")
    return "\n".join(lines)

def transactionTestingStats(transactions: List[Transaction]) -> Generator[str, None, None]:
    countByAccount = Counter(t.account for t in transactions)
    yield "countByAccount:"
    for account in sorted(countByAccount.keys()):
        yield f"  {account}: {countByAccount[account]}"
    yield ""

    yield "totalAccountBalance:"
    yield totalAccountBalance(transactions).longDescription
    for account, balance in accountBalanceByAccount(transactions).items():
        yield f"Account balance for {account}:"
        yield balance.longDescription
    yield ""

    yield "netWorth:"
    yield netWorth(transactions).longDescription
    yield ""

    yield "totalSaving:"
    yield totalSaving(transactions).longDescription
    yield ""

    def adjustedTotalOf(exactCategory: Category, isForecast: bool):
        return MoneyAmount(JPY, totalAdjustedAmountAsJPY(
            t for t in transactions
            if t.category == exactCategory and t.isForecast == isForecast
        ))
    for cat in ORDERED_BASE_CATEGORIES:
        prefix = "Adjusted amount total (non-forecast)"
        yield f"{prefix} {cat.label}: {adjustedTotalOf(cat, isForecast=False)}"
    yield ""
    for cat in ORDERED_BASE_CATEGORIES:
        prefix = "Adjusted amount total (forecast)"
        yield f"{prefix} {cat.label}: {adjustedTotalOf(cat, isForecast=True)}"
    yield ""

def writeTransactionsWithStat(
    transactions: List[Transaction],
    path: Path,
    transformString: Callable[[str], str],
    pretty: bool = False
):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(
            transformString(line) + "\n"
            for line in transactionTestingStats(transactions)
        )
        f.writelines(
            "\n" + transformString(transactionRepr(t, pretty=pretty)) + "\n"
            for t in transactions
        )
