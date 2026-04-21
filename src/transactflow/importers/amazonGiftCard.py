from dataclasses import dataclass, replace

from ..base import (
    AMAZON_GIFT_CARD,
    JPY,
    Date,
    MoneyAmount,
    Transaction,
    sortedByDate,
)
from ..importers.importer import addingCutoffTransactionTo
from ..process import funcMatching, takeFirstMatch


@dataclass
class AmazonPayAnnotation:
    date: Date
    jpyAmount: float
    description: str


def annotateAmazonGiftCardTransactions(
    transactions: list[Transaction],
    amazonGiftCardLastUpdateDate: Date,
    amazonPayAnnotations: list[AmazonPayAnnotation],
    amazonPayAnnotationsLastUpdateDate: Date,
) -> list[Transaction]:
    remaining = [t for t in transactions]
    annotated: list[Transaction] = []
    for annotation in amazonPayAnnotations:

        @funcMatching(f"Matching annotation: {annotation!r}")
        def matchingAnnotation(t: Transaction) -> bool:
            return t.date == annotation.date and t.rawAmount == MoneyAmount(
                JPY, annotation.jpyAmount
            )

        matched, remaining = takeFirstMatch(remaining, matchingAnnotation)
        # Not all Amazon Pay items have a corresponding gift card transaction, because Amazon Pay
        # can charge from a card directly.
        # assert(matched is not None)
        if matched is None:
            continue
        annotated.append(
            replace(
                matched,
                description=(
                    f"AmazonPayAnnotation: {annotation.description}, "
                    + f"original: {matched.description}"
                ),
            )
        )
    results = sortedByDate(annotated + remaining)
    assert len(results) == len(transactions)

    cutoffDate = amazonGiftCardLastUpdateDate
    assert cutoffDate == amazonPayAnnotationsLastUpdateDate
    return addingCutoffTransactionTo(results, date=cutoffDate, account=AMAZON_GIFT_CARD)
