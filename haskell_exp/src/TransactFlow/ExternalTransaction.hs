module TransactFlow.ExternalTransaction
  ( toExternalTransaction,
    fromExternalTransaction,
    categoryToProto,
    categoryFromProto,
  )
where

import Data.ProtoLens (defMessage)
import Data.Text (Text)
import Data.Time.Calendar (Day, fromGregorian, toGregorian)
import Data.Vector.Unboxed qualified as VU
import Lens.Family2 (view, (&), (.~))
import Proto.Transactflow qualified as P
import Proto.Transactflow_Fields qualified as F
import TransactFlow.Base

--------------------------------------------------------------------------------
-- To Proto
--------------------------------------------------------------------------------

categoryToProto :: Category -> P.Category
categoryToProto cat =
  defMessage
    & F.label .~ cat.label
    & F.maybe'parent .~ fmap categoryToProto cat.parent

exchangeRatesToProto :: ExchangeRates -> P.ExchangeRates
exchangeRatesToProto er =
  defMessage
    & F.maybe'usdJpyRate .~ er.usdJPYRate
    & F.maybe'usdPerStockUnitShare .~ er.usdPerStockUnitShare

dayToProto :: Day -> P.Date
dayToProto d =
  let (y, m, dy) = toGregorian d
   in defMessage
        & F.year .~ fromIntegral y
        & F.month .~ fromIntegral m
        & F.day .~ fromIntegral dy

moneyAmountToProto :: MoneyAmount -> P.MoneyAmount
moneyAmountToProto amt =
  defMessage
    & F.currency .~ (defMessage & F.label .~ amt.currency.label)
    & F.quantity .~ amt.quantity

sourceLocationToProto :: (Text, Int) -> P.SourceLocation
sourceLocationToProto (fp, ln) =
  defMessage
    & F.filePath .~ fp
    & F.lineNumber .~ fromIntegral ln

toExternalTransaction :: Transaction -> P.ExternalTransaction
toExternalTransaction t =
  defMessage
    & F.date .~ dayToProto t.date
    & F.description .~ t.description
    & F.rawAmount .~ moneyAmountToProto t.rawAmount
    & F.account .~ t.account
    & F.rawRecord .~ t.rawRecord
    & F.maybe'sourceLocation .~ fmap sourceLocationToProto t.sourceLocation
    & F.category .~ categoryToProto t.category
    & F.maybe'relatedTo .~ t.relatedTo
    & F.vec'adjustments .~ VU.fromList t.adjustments
    & F.maybe'comment .~ t.comment
    & F.exchangeRates .~ exchangeRatesToProto t.exchangeRates
    & F.isUnrealized .~ t.isUnrealized
    & F.isForecast .~ t.isForecast

--------------------------------------------------------------------------------
-- From Proto
--------------------------------------------------------------------------------

categoryFromProto :: P.Category -> Category
categoryFromProto pc =
  Category
    { label = view F.label pc,
      parent = fmap categoryFromProto (view F.maybe'parent pc)
    }

exchangeRatesFromProto :: P.ExchangeRates -> ExchangeRates
exchangeRatesFromProto per =
  ExchangeRates
    { usdJPYRate = view F.maybe'usdJpyRate per,
      usdPerStockUnitShare = view F.maybe'usdPerStockUnitShare per
    }

dayFromProto :: P.Date -> Day
dayFromProto pd =
  fromGregorian
    (fromIntegral (view F.year pd))
    (fromIntegral (view F.month pd))
    (fromIntegral (view F.day pd))

moneyAmountFromProto :: P.MoneyAmount -> MoneyAmount
moneyAmountFromProto pma =
  MoneyAmount
    { currency = Currency (view F.label (view F.currency pma)),
      quantity = view F.quantity pma
    }

sourceLocationFromProto :: P.SourceLocation -> (Text, Int)
sourceLocationFromProto psl =
  (view F.filePath psl, fromIntegral (view F.lineNumber psl))

fromExternalTransaction :: P.ExternalTransaction -> Transaction
fromExternalTransaction et =
  Transaction
    { date = dayFromProto (view F.date et),
      description = view F.description et,
      rawAmount = moneyAmountFromProto (view F.rawAmount et),
      account = view F.account et,
      rawRecord = view F.rawRecord et,
      sourceLocation = fmap sourceLocationFromProto (view F.maybe'sourceLocation et),
      category = categoryFromProto (view F.category et),
      relatedTo = view F.maybe'relatedTo et,
      adjustments = VU.toList (view F.vec'adjustments et),
      comment = view F.maybe'comment et,
      exchangeRates = exchangeRatesFromProto (view F.exchangeRates et),
      isUnrealized = view F.isUnrealized et,
      isForecast = view F.isForecast et
    }
