module TransactFlow.Base
  ( -- * Core type aliases
    Account,

    -- * Currency
    Currency (..),
    jpy,
    usd,
    cny,
    stockUnit,
    emptyCurrency,

    -- * MoneyAmount
    MoneyAmount (..),
    emptyAmount,
    addAmounts,
    subtractAmounts,
    scaleAmount,
    negateAmount,
    absAmount,
    amountsHaveSameCurrency,
    sumSingleCurrencyAmounts,

    -- * Category
    Category (..),
    mkCategory,
    mkSubCategory,
    isUnder,
    isUnderAny,
    ancestorBy,
    categoryDepth,

    -- * Transaction
    Transaction (..),
    adjustedAmount,
    replacingAccount,
    replacingCategory,
    replacingRelatedTo,
    replacingDescription,
    replacingComment,
    addingAdjustment,
    SynthesizedTx (..),
    defaultSynthesizedTx,
    synthesizedTransaction,
    sortedByDate,

    -- * ExchangeRates
    ExchangeRates (..),
    emptyExchangeRates,

    -- * Utilities
    mapOptional,
  )
where

import Data.List (sortOn)
import Data.Text (Text)
import Data.Time.Calendar (Day)

-- | Account is simply a label.
type Account = Text

--------------------------------------------------------------------------------
-- Currency
--------------------------------------------------------------------------------

newtype Currency = Currency {label :: Text}
  deriving (Eq, Ord, Show)

jpy, usd, cny, stockUnit, emptyCurrency :: Currency
jpy = Currency "JPY"
usd = Currency "USD"
cny = Currency "CNY"
stockUnit = Currency "STOCK_UNIT"
emptyCurrency = Currency "Empty Currency"

--------------------------------------------------------------------------------
-- MoneyAmount
--------------------------------------------------------------------------------

data MoneyAmount = MoneyAmount
  { currency :: Currency,
    quantity :: Double
  }
  deriving (Show)

-- | Two MoneyAmounts are equal when both are zero-quantity, or when currency
-- and quantity match. Mirrors the Python __eq__.
instance Eq MoneyAmount where
  a == b
    | a.quantity == 0 && b.quantity == 0 = True
    | otherwise = a.currency == b.currency && a.quantity == b.quantity

emptyAmount :: MoneyAmount
emptyAmount = MoneyAmount emptyCurrency 0

addAmounts :: MoneyAmount -> MoneyAmount -> MoneyAmount
addAmounts a b
  | a.currency == emptyCurrency = b
  | b.currency == emptyCurrency = a
  | a.currency == b.currency = MoneyAmount a.currency (a.quantity + b.quantity)
  | otherwise = error "addAmounts: currency mismatch"

subtractAmounts :: MoneyAmount -> MoneyAmount -> MoneyAmount
subtractAmounts a b = addAmounts a (negateAmount b)

scaleAmount :: Double -> MoneyAmount -> MoneyAmount
scaleAmount s (MoneyAmount c q) = MoneyAmount c (s * q)

negateAmount :: MoneyAmount -> MoneyAmount
negateAmount = scaleAmount (-1)

absAmount :: MoneyAmount -> MoneyAmount
absAmount (MoneyAmount c q) = MoneyAmount c (abs q)

amountsHaveSameCurrency :: [MoneyAmount] -> Bool
amountsHaveSameCurrency amounts =
  let nonEmpty = filter (/= emptyAmount) amounts
      currencies = map (.currency) nonEmpty
   in case currencies of
        [] -> True
        (c : _) -> all (== c) currencies

sumSingleCurrencyAmounts :: [MoneyAmount] -> MoneyAmount
sumSingleCurrencyAmounts = foldl addAmounts emptyAmount

--------------------------------------------------------------------------------
-- Category
--------------------------------------------------------------------------------

-- | A hierarchical category. Identity is based on label only.
data Category = Category
  { label :: Text,
    parent :: Maybe Category
  }
  deriving (Show)

instance Eq Category where
  a == b = a.label == b.label

instance Ord Category where
  compare a b = compare a.label b.label

mkCategory :: Text -> Category
mkCategory label = Category label Nothing

mkSubCategory :: Text -> Category -> Category
mkSubCategory label parent = Category label (Just parent)

-- | Check if this category is the given ancestor, or a descendant of it.
isUnder :: Category -> Category -> Bool
isUnder cat ancestor
  | cat == ancestor = True
  | otherwise = case cat.parent of
      Nothing -> False
      Just p -> isUnder p ancestor

-- | Check if this category is under any of the given ancestors.
isUnderAny :: Category -> [Category] -> Bool
isUnderAny cat = any (isUnder cat)

-- | Walk up the parent chain by the given number of levels.
ancestorBy :: Int -> Category -> Category
ancestorBy 0 cat = cat
ancestorBy n cat = case cat.parent of
  Nothing -> cat
  Just p -> ancestorBy (n - 1) p

-- | Depth of the category in its hierarchy (root = 0).
categoryDepth :: Category -> Int
categoryDepth cat = case cat.parent of
  Nothing -> 0
  Just p -> 1 + categoryDepth p

--------------------------------------------------------------------------------
-- ExchangeRates
--------------------------------------------------------------------------------

data ExchangeRates = ExchangeRates
  { usdJPYRate :: Maybe Double,
    usdPerStockUnitShare :: Maybe Double
  }
  deriving (Eq, Show)

emptyExchangeRates :: ExchangeRates
emptyExchangeRates = ExchangeRates Nothing Nothing

--------------------------------------------------------------------------------
-- Transaction
--------------------------------------------------------------------------------

data Transaction = Transaction
  { date :: Day,
    description :: Text,
    rawAmount :: MoneyAmount,
    account :: Account,
    originalFormat :: Text,
    sourceLocation :: Maybe (Text, Int),
    category :: Category,
    -- Extension fields
    relatedTo :: Maybe Account,
    adjustments :: [Double],
    comment :: Maybe Text,
    exchangeRates :: ExchangeRates,
    isUnrealized :: Bool,
    isForecast :: Bool
  }
  deriving (Show)

-- | The effective amount after applying all adjustments.
adjustedAmount :: Transaction -> MoneyAmount
adjustedAmount t =
  let raw = t.rawAmount
      adj = sum t.adjustments
   in MoneyAmount raw.currency (raw.quantity + adj)

-- Record update helpers (Haskell records are already immutable, these mirror
-- the Python replacing* methods for API familiarity).

replacingAccount :: Account -> Transaction -> Transaction
replacingAccount acc t = t {account = acc}

replacingCategory :: Category -> Transaction -> Transaction
replacingCategory cat t = t {category = cat}

replacingRelatedTo :: Account -> Transaction -> Transaction
replacingRelatedTo rel t = t {relatedTo = Just rel}

replacingDescription :: Text -> Transaction -> Transaction
replacingDescription desc t = t {description = desc}

replacingComment :: Text -> Transaction -> Transaction
replacingComment c t = t {comment = Just c}

addingAdjustment :: Double -> Transaction -> Transaction
addingAdjustment adj t = t {adjustments = t.adjustments ++ [adj]}

-- | Parameters for creating a synthesized (artificial) transaction.
data SynthesizedTx = SynthesizedTx
  { synthDate :: Day,
    synthDescription :: Text,
    synthAmount :: MoneyAmount,
    synthCategory :: Category,
    synthAccount :: Account,
    synthAmountIsRaw :: Bool,
    synthRelatedTo :: Maybe Account,
    synthIsUnrealized :: Bool,
    synthIsForecast :: Bool,
    synthExchangeRates :: ExchangeRates
  }
  deriving (Show)

-- | Default with all optional fields set to safe values.
-- Caller must override synthDate, synthDescription, synthAmount,
-- synthCategory, and synthAccount.
defaultSynthesizedTx :: SynthesizedTx
defaultSynthesizedTx =
  SynthesizedTx
    { synthDate = toEnum 0,
      synthDescription = "",
      synthAmount = emptyAmount,
      synthCategory = mkCategory "",
      synthAccount = "",
      synthAmountIsRaw = False,
      synthRelatedTo = Nothing,
      synthIsUnrealized = False,
      synthIsForecast = False,
      synthExchangeRates = emptyExchangeRates
    }

-- | Create a synthesized (artificial) transaction. When synthAmountIsRaw is
-- False, the raw amount is set to zero and the quantity goes into adjustments.
synthesizedTransaction :: SynthesizedTx -> Transaction
synthesizedTransaction p =
  let (raw, adjs)
        | p.synthAmountIsRaw = (p.synthAmount, [])
        | otherwise = (MoneyAmount p.synthAmount.currency 0, [p.synthAmount.quantity])
   in Transaction
        { date = p.synthDate,
          description = p.synthDescription,
          rawAmount = raw,
          account = p.synthAccount,
          originalFormat = "",
          sourceLocation = Nothing,
          category = p.synthCategory,
          relatedTo = p.synthRelatedTo,
          adjustments = adjs,
          comment = Nothing,
          exchangeRates = p.synthExchangeRates,
          isUnrealized = p.synthIsUnrealized,
          isForecast = p.synthIsForecast
        }

sortedByDate :: [Transaction] -> [Transaction]
sortedByDate = sortOn (.date)

--------------------------------------------------------------------------------
-- Utilities
--------------------------------------------------------------------------------

mapOptional :: Maybe a -> (a -> b) -> Maybe b
mapOptional = flip fmap
