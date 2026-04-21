import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory

from .analysis import (
    ANY_CATEGORY,
    AnalysisProvider,
    AnalysisProviderFilter,
    AnalysisProviderOptions,
    AnnotatedCategory,
    BarChartData,
    CategorizeOption,
    DeductIncomeOption,
    GroupLabelOption,
    GroupLabelRange,
    LabelSetAlias,
    PieChartData,
    PseudoCategory,
    SegmentedDisplayOption,
    TransactionSetStats,
)
from .base import (
    EXCLUDED_INCOME,
    INTERNAL_TRANSFER,
    ORDERED_ACCOUNTS,
    ORDERED_BASE_CATEGORIES,
    Category,
    MoneyAmount,
    Transaction,
    colorCodeForJPYAmount,
)
from .colors import COLORS, XKCD_TO_HEX
from .multiCurrency import amountInJPY, embeddedOrNearestRatesFor
from .serialization import categoryForLabel
from .userConfig import UserConfig

packageDir = Path(__file__).parent
templateDir = str(packageDir / "templates")
webDir = packageDir / "web"
distDir = webDir / "dist"
app = Flask(
    __name__,
    static_folder=str(distDir),
    static_url_path="/static",
    template_folder=templateDir,
)


def buildFrontend() -> None:
    """Compile the TypeScript frontend and stage vendor assets into `web/dist/`."""
    tsconfig = webDir / "tsconfig.json"
    if not tsconfig.is_file():
        raise RuntimeError(f"Missing tsconfig at {tsconfig}")
    nodeModules = webDir / "node_modules"
    localTsc = nodeModules / ".bin" / "tsc"
    plotlySrc = nodeModules / "plotly.js-dist-min" / "plotly.min.js"
    if not localTsc.is_file() or not plotlySrc.is_file():
        raise RuntimeError(
            f"Frontend dependencies not installed. "
            f"Run `npm install` in {webDir} first."
        )
    distDir.mkdir(exist_ok=True)
    print(f"[analysisServer] Compiling frontend: {webDir}", file=sys.stderr)
    subprocess.run(
        [str(localTsc), "-p", str(webDir)],
        check=True,
    )
    def copyIfNewer(src: Path, dst: Path) -> None:
        if (not dst.is_file()
                or dst.stat().st_mtime < src.stat().st_mtime):
            shutil.copy2(src, dst)
    copyIfNewer(plotlySrc, distDir / "plotly.min.js")
    copyIfNewer(webDir / "app.css", distDir / "app.css")

provider: Optional[AnalysisProvider] = None

DEFAULT_FALLBACK_COLOR = "#888888"


def initProvider(config: UserConfig) -> None:
    global provider
    from .processes.runAll import run

    trans = run(config)
    assert config.stock is not None
    provider = AnalysisProvider(trans, config)


# ---------------------------------------------------------------------------
# Shared helpers (used across multiple routes)
# ---------------------------------------------------------------------------


def categoryColor(category: Category) -> str:
    xkcd = COLORS.get(category)
    if xkcd is None:
        return DEFAULT_FALLBACK_COLOR
    return XKCD_TO_HEX.get(xkcd, DEFAULT_FALLBACK_COLOR)


def annotatedCategoryToDict(ac: AnnotatedCategory) -> Dict[str, Any]:
    return {
        "label": ac.label,
        "categoryLabel": ac.category.label,
        "isForecast": ac.isForecast,
        "color": categoryColor(ac.category),
    }


def parseEnum(enumType, raw: Any, default):
    if raw is None or raw == "":
        return default
    if raw in enumType.__members__:
        return enumType[raw]
    return enumType(raw)


def parseOptions(body: Dict[str, Any]) -> AnalysisProviderOptions:
    def parseLabelOption(raw: Any) -> Optional[GroupLabelOption]:
        if raw is None:
            return None
        if isinstance(raw, dict):
            kind = raw.get("kind")
            if kind == "label":
                return raw["value"]
            if kind == "alias":
                return LabelSetAlias[raw["value"]]
            if kind == "range":
                return GroupLabelRange(
                    fromLabel=raw["fromLabel"], toLabel=raw["toLabel"]
                )
            raise ValueError(f"Unknown labelOption kind: {kind!r}")
        if isinstance(raw, str):
            if raw in LabelSetAlias.__members__:
                return LabelSetAlias[raw]
            return raw
        raise ValueError(f"Unsupported labelOption: {raw!r}")

    def parseFilter(raw: Optional[Dict[str, Any]]) -> AnalysisProviderFilter:
        raw = raw or {}
        categoryFilterRaw = raw.get("categoryFilter")
        if categoryFilterRaw in (None, "", ANY_CATEGORY.label):
            categoryFilter = None
        else:
            categoryFilter = categoryForLabel(categoryFilterRaw)
        recordAccount = raw.get("recordAccount") or None
        descriptionContains = raw.get("descriptionContains") or None
        return AnalysisProviderFilter(
            labelOption=parseLabelOption(raw.get("labelOption")),
            descriptionContains=descriptionContains,
            categoryFilter=categoryFilter,
            exactMatchCategory=bool(raw.get("exactMatchCategory", False)),
            recordAccount=recordAccount,
            segmentedDisplayOption=parseEnum(
                SegmentedDisplayOption,
                raw.get("segmentedDisplayOption"),
                SegmentedDisplayOption.NO_SPEC,
            ),
            amountQuantityFrom=raw.get("amountQuantityFrom"),
            amountQuantityUntil=raw.get("amountQuantityUntil"),
            filterByRawAmount=bool(raw.get("filterByRawAmount", False)),
        )

    filterVal = parseFilter(body.get("filter"))
    categorizeOption = parseEnum(
        CategorizeOption,
        body.get("categorizeOption"),
        CategorizeOption.ORIGINAL,
    )
    return AnalysisProviderOptions(filter=filterVal, categorizeOption=categorizeOption)


def requireProvider() -> AnalysisProvider:
    if provider is None:
        raise RuntimeError("Analysis provider not initialized")
    return provider


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return send_from_directory(templateDir, "index.html")


@app.route("/api/meta")
def meta():
    def enumOptions(enumType) -> List[Dict[str, str]]:
        return [{"name": e.name, "value": e.value} for e in enumType]

    def categoryOptions() -> List[Dict[str, Any]]:
        baseCats: List[Category] = [ANY_CATEGORY] + list(ORDERED_BASE_CATEGORIES)
        return [
            {
                "label": c.label,
                "parentLabel": c.parent.label if c.parent is not None else None,
                "depth": c.depth,
                "isPseudo": isinstance(c, PseudoCategory),
                "color": categoryColor(c),
            }
            for c in baseCats
        ]

    def categoryColorsMap() -> Dict[str, str]:
        return {cat.label: categoryColor(cat) for cat in COLORS.keys()}

    p = requireProvider()
    return jsonify(
        {
            "labels": p.labels,
            "labelSetAliases": enumOptions(LabelSetAlias),
            "categories": categoryOptions(),
            "accounts": ORDERED_ACCOUNTS,
            "segmentedDisplayOptions": enumOptions(SegmentedDisplayOption),
            "categorizeOptions": enumOptions(CategorizeOption),
            "deductIncomeOptions": enumOptions(DeductIncomeOption),
            "categoryColors": categoryColorsMap(),
            "anyCategoryLabel": ANY_CATEGORY.label,
            "rates": {
                "JPYCNYRate": p.rates.JPYCNYRate,
                "USDJPYRate": p.rates.USDJPYRate,
            },
        }
    )


@app.route("/api/overview")
def overview():
    p = requireProvider()
    labelsForOverview = ["All"] + [
        l for l in p.labels if l.isnumeric() and len(l) == 4
    ]
    groupOverviews = [
        {"label": label, "text": p.groupOverview(label)}
        for label in labelsForOverview
    ]
    return jsonify(
        {
            "groupOverviews": groupOverviews,
            "netTotalsReport": p.netTotalsReport(),
        }
    )


@app.route("/api/transactions", methods=["POST"])
def transactions():
    def moneyAmountToDict(amount: MoneyAmount) -> Dict[str, Any]:
        return {"currency": amount.currency.label, "quantity": amount.quantity}

    def transactionAmountJPY(t: Transaction) -> Optional[float]:
        if any(
            t.category.isUnder(cat)
            for cat in [EXCLUDED_INCOME, INTERNAL_TRANSFER]
        ):
            return None
        try:
            return amountInJPY(t.adjustedAmount, embeddedOrNearestRatesFor(t))
        except AssertionError:
            return None

    def transactionToDict(t: Transaction) -> Dict[str, Any]:
        adjustedJPY = transactionAmountJPY(t)
        colorCode = (
            colorCodeForJPYAmount(adjustedJPY) if adjustedJPY is not None else None
        )
        sourceLocation = None
        if t.sourceLocation is not None:
            filename, line = t.sourceLocation
            sourceLocation = {"filename": filename, "line": line}
        return {
            "date": t.date.isoformat(),
            "description": t.description,
            "account": t.account,
            "relatedTo": t.relatedTo,
            "category": t.category.label,
            "rawAmount": moneyAmountToDict(t.rawAmount),
            "adjustedAmount": moneyAmountToDict(t.adjustedAmount),
            "adjustedAmountJPY": adjustedJPY,
            "isForecast": t.isForecast,
            "isUnrealized": t.isUnrealized,
            "comment": t.comment,
            "sourceLocation": sourceLocation,
            "rowColorCode": colorCode,
        }

    p = requireProvider()
    body = request.get_json() or {}
    options = parseOptions(body)
    limit = int(body.get("limit", 600))

    stats = TransactionSetStats(p.matchingTransactions(options))
    selected = stats.transactions
    truncated = False
    if limit > 0 and len(selected) > limit:
        truncated = True
        selected = selected[:limit]
    totalRawJPY = stats.totalRawAmountAsJPYFor(selected)
    totalAdjustedJPY = stats.totalAdjustedAmountAsJPYFor(selected)

    return jsonify(
        {
            "transactions": [transactionToDict(t) for t in selected],
            "totalCount": len(stats.transactions),
            "returnedCount": len(selected),
            "truncated": truncated,
            "totalRawAmountJPY": totalRawJPY,
            "totalAdjustedAmountJPY": totalAdjustedJPY,
        }
    )


@app.route("/api/barChartData", methods=["POST"])
def barChartData():
    def barChartResponse(data: BarChartData) -> Dict[str, Any]:
        def seriesFor(
            cats: List[AnnotatedCategory],
            totals: List[Dict[AnnotatedCategory, float]],
        ) -> List[Dict[str, Any]]:
            return [
                {
                    "category": annotatedCategoryToDict(c),
                    "values": [d.get(c, 0) for d in totals],
                }
                for c in cats
            ]

        return {
            "labels": data.labels,
            "incomeSeries": seriesFor(data.orderedIncomeCats, data.incomeTotalsByCat),
            "expenseSeries": seriesFor(data.orderedExpenseCats, data.expenseTotalsByCat),
        }

    p = requireProvider()
    body = request.get_json() or {}
    options = parseOptions(body)
    deductOption = parseEnum(
        DeductIncomeOption,
        body.get("deductIncomeOption"),
        DeductIncomeOption.NO_DEDUCTION,
    )
    data = p.barChartData(options, deductOption)
    return jsonify(barChartResponse(data))


@app.route("/api/pieChartData", methods=["POST"])
def pieChartData():
    def pieChartResponse(data: PieChartData) -> Dict[str, Any]:
        orderedPairs = data.orderedCategoryToAmountPairs
        totalMagnitude = sum(abs(am) for _, am in orderedPairs) or 1.0
        entries = [
            {
                **annotatedCategoryToDict(c),
                "amount": am,
                "fraction": abs(am) / totalMagnitude,
            }
            for c, am in orderedPairs
        ]
        otherEntries: Optional[List[Dict[str, Any]]] = None
        orderedOther = data.orderedOtherCategoryToAmount
        if orderedOther is not None:
            otherTotal = sum(abs(am) for _, am in orderedOther) or 1.0
            otherEntries = [
                {
                    **annotatedCategoryToDict(c),
                    "amount": am,
                    "fraction": abs(am) / otherTotal,
                }
                for c, am in orderedOther
            ]
        return {
            "labels": data.labels,
            "entries": entries,
            "otherEntries": otherEntries,
            "isGroupAverage": data.isGroupAverage,
            "total": sum(am for _, am in orderedPairs),
            "longDescription": data.longDescription,
        }

    p = requireProvider()
    body = request.get_json() or {}
    options = parseOptions(body)
    deductOption = parseEnum(
        DeductIncomeOption,
        body.get("deductIncomeOption"),
        DeductIncomeOption.NO_DEDUCTION,
    )
    includeRemaining = bool(body.get("includeRemaining", False))
    averageByGroup = bool(body.get("averageByGroup", False))
    data = p.pieChartData(options, deductOption, includeRemaining, averageByGroup)
    if data is None:
        return jsonify(None)
    return jsonify(pieChartResponse(data))


@app.route("/api/shopDistribution", methods=["POST"])
def shopDistribution():
    p = requireProvider()
    body = request.get_json() or {}
    options = parseOptions(body)
    deductOption = parseEnum(
        DeductIncomeOption,
        body.get("deductIncomeOption"),
        DeductIncomeOption.NO_DEDUCTION,
    )
    shops = p.dataForShopDistribution(options, deductOption)
    return jsonify({"shops": [{"name": n, "amount": am} for n, am in shops]})


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run(
    config: UserConfig,
    host: str = "127.0.0.1",
    port: int = 5000,
    debug: bool = False,
) -> None:
    """
    Initialize the analysis provider from `config` and start the Flask server.

    Blocks until the server stops.
    """
    buildFrontend()
    initProvider(config)
    app.run(host=host, port=port, debug=debug)


def runFromCli() -> None:
    import argparse
    import importlib.util

    parser = argparse.ArgumentParser(description="Run the TransactFlow analysis server.")
    parser.add_argument(
        "--config", required=True,
        help="Path to a Python file exposing USER_CONFIG.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5000, type=int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location("userConfigModule", args.config)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run(module.USER_CONFIG, host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    runFromCli()
