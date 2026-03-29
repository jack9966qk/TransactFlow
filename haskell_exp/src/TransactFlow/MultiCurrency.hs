{- HLINT ignore "Redundant bracket" -}
module TransactFlow.MultiCurrency
  ( MultiCurrencyAmount (..),
    emptyMultiCurrency,
    addMultiCurrency,
    subtractMultiCurrency,
    scaleMultiCurrency,
    negateMultiCurrency,
    absMultiCurrency,
    fromMoneyAmount,
    addMoneyAmount,
    pruneZeroes,
    sumCurrencyAmounts,
    totalRawAmount,
    totalAdjustedAmount,
  )
where

import Data.Map.Strict (Map)
import Data.Map.Strict qualified as Map
import TransactFlow.Base

--------------------------------------------------------------------------------
-- MultiCurrencyAmount
--------------------------------------------------------------------------------

-- | Holds quantities across multiple currencies.
newtype MultiCurrencyAmount = MultiCurrencyAmount
  { quantities :: Map Currency Double
  }
  deriving (Show)

instance Eq MultiCurrencyAmount where
  a == b = (pruneZeroes a).quantities == (pruneZeroes b).quantities

emptyMultiCurrency :: MultiCurrencyAmount
emptyMultiCurrency = MultiCurrencyAmount Map.empty

fromMoneyAmount :: MoneyAmount -> MultiCurrencyAmount
fromMoneyAmount amt = MultiCurrencyAmount (Map.singleton amt.currency amt.quantity)

addMultiCurrency :: MultiCurrencyAmount -> MultiCurrencyAmount -> MultiCurrencyAmount
addMultiCurrency a b =
  MultiCurrencyAmount (Map.unionWith (+) a.quantities b.quantities)

subtractMultiCurrency :: MultiCurrencyAmount -> MultiCurrencyAmount -> MultiCurrencyAmount
subtractMultiCurrency a b = addMultiCurrency a (negateMultiCurrency b)

scaleMultiCurrency :: Double -> MultiCurrencyAmount -> MultiCurrencyAmount
scaleMultiCurrency s mca =
  MultiCurrencyAmount (Map.map (* s) mca.quantities)

negateMultiCurrency :: MultiCurrencyAmount -> MultiCurrencyAmount
negateMultiCurrency = scaleMultiCurrency (-1)

absMultiCurrency :: MultiCurrencyAmount -> MultiCurrencyAmount
absMultiCurrency mca =
  MultiCurrencyAmount (Map.map abs mca.quantities)

-- | Add a single MoneyAmount into a MultiCurrencyAmount.
addMoneyAmount :: MoneyAmount -> MultiCurrencyAmount -> MultiCurrencyAmount
addMoneyAmount amt mca = addMultiCurrency mca (fromMoneyAmount amt)

-- | Remove entries with zero quantity.
pruneZeroes :: MultiCurrencyAmount -> MultiCurrencyAmount
pruneZeroes mca =
  MultiCurrencyAmount (Map.filter (/= 0) mca.quantities)

-- | Sum a list of MoneyAmounts into a MultiCurrencyAmount.
sumCurrencyAmounts :: [MoneyAmount] -> MultiCurrencyAmount
sumCurrencyAmounts = pruneZeroes . foldl (flip addMoneyAmount) emptyMultiCurrency

-- | Total raw amounts across all transactions.
totalRawAmount :: [Transaction] -> MultiCurrencyAmount
totalRawAmount = sumCurrencyAmounts . map (.rawAmount)

-- | Total adjusted amounts across all transactions.
totalAdjustedAmount :: [Transaction] -> MultiCurrencyAmount
totalAdjustedAmount = sumCurrencyAmounts . map adjustedAmount
