"""Conversions between native Transaction types and protobuf ExternalTransaction."""

from typing import Optional, Tuple

from .base import (
    Account, Category, Currency, Date, ExchangeRates, MoneyAmount,
    Transaction, EMPTY_EXCHANGE_RATES,
)
from .proto_gen import transactflow_pb2 as pb


def _categoryToProto(cat: Category) -> pb.Category:
    if cat.parent is not None:
        return pb.Category(label=cat.label, parent=_categoryToProto(cat.parent))
    return pb.Category(label=cat.label)


def _categoryFromProto(cat: pb.Category) -> Category:
    parent = None
    if cat.HasField("parent"):
        parent = _categoryFromProto(cat.parent)
    return Category(label=cat.label, parent=parent)


def _exchangeRatesToProto(er: ExchangeRates) -> pb.ExchangeRates:
    kwargs = {}
    if er.USDJPYRate is not None:
        kwargs["usd_jpy_rate"] = er.USDJPYRate
    if er.USDPerStockUnitShare is not None:
        kwargs["usd_per_stock_unit_share"] = er.USDPerStockUnitShare
    return pb.ExchangeRates(**kwargs)


def _exchangeRatesFromProto(er: pb.ExchangeRates) -> ExchangeRates:
    usdJpy = er.usd_jpy_rate if er.HasField("usd_jpy_rate") else None
    usdStock = er.usd_per_stock_unit_share if er.HasField("usd_per_stock_unit_share") else None
    return ExchangeRates(USDJPYRate=usdJpy, USDPerStockUnitShare=usdStock)


def toExternalTransaction(t: Transaction) -> pb.ExternalTransaction:
    """Convert a native Transaction to a protobuf ExternalTransaction."""
    protoDate = pb.Date(year=t.date.year, month=t.date.month, day=t.date.day)
    protoRawAmount = pb.MoneyAmount(
        currency=pb.Currency(label=t.rawAmount.currency.label),
        quantity=t.rawAmount.quantity,
    )
    protoCategory = _categoryToProto(t.category)
    protoExchangeRates = _exchangeRatesToProto(t.referencedExchangeRates)

    kwargs: dict = dict(
        date=protoDate,
        description=t.description,
        raw_amount=protoRawAmount,
        account=t.account,
        raw_record=t.rawRecord,
        category=protoCategory,
        adjustments=list(t.adjustments),
        exchange_rates=protoExchangeRates,
        is_unrealized=t.isUnrealized,
        is_forecast=t.isForecast,
    )

    if t.sourceLocation is not None:
        kwargs["source_location"] = pb.SourceLocation(
            file_path=t.sourceLocation[0],
            line_number=t.sourceLocation[1],
        )
    if t.relatedTo is not None:
        kwargs["related_to"] = t.relatedTo
    if t.comment is not None:
        kwargs["comment"] = t.comment

    return pb.ExternalTransaction(**kwargs)


def fromExternalTransaction(et: pb.ExternalTransaction) -> Transaction:
    """Convert a protobuf ExternalTransaction to a native Transaction."""
    txDate = Date(year=et.date.year, month=et.date.month, day=et.date.day)

    rawAmount = MoneyAmount(
        currency=Currency(et.raw_amount.currency.label),
        quantity=et.raw_amount.quantity,
    )

    category = _categoryFromProto(et.category)
    exchangeRates = _exchangeRatesFromProto(et.exchange_rates)

    sourceLocation: Optional[Tuple[str, int]] = None
    if et.HasField("source_location"):
        sourceLocation = (et.source_location.file_path, et.source_location.line_number)

    relatedTo: Optional[Account] = None
    if et.HasField("related_to"):
        relatedTo = et.related_to

    comment: Optional[str] = None
    if et.HasField("comment"):
        comment = et.comment

    return Transaction(
        date=txDate,
        description=et.description,
        rawAmount=rawAmount,
        account=et.account,
        rawRecord=et.raw_record,
        sourceLocation=sourceLocation,
        category=category,
        relatedTo=relatedTo,
        adjustments=tuple(et.adjustments),
        comment=comment,
        referencedExchangeRates=exchangeRates,
        isUnrealized=et.is_unrealized,
        isForecast=et.is_forecast,
    )
