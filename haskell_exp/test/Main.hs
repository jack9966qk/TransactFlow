{- HLINT ignore "Redundant bracket" -}
module Main (main) where

import Data.Map.Strict qualified as Map
import Data.Text (Text)
import Data.Time.Calendar (Day, fromGregorian)
import TransactFlow.Base
import TransactFlow.MultiCurrency
import TransactFlow.Process

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

assert :: String -> Bool -> IO ()
assert label True = putStrLn $ "  PASS: " <> label
assert label False = error $ "  FAIL: " <> label

data MkTx = MkTx
  { on :: Day,
    desc :: Text,
    amount :: Double,
    cat :: Category,
    fromAcct :: Account
  }

mkTx :: MkTx -> Transaction
mkTx p =
  Transaction
    { date = p.on,
      description = p.desc,
      rawAmount = MoneyAmount jpy p.amount,
      account = p.fromAcct,
      originalFormat = "",
      sourceLocation = Nothing,
      category = p.cat,
      relatedTo = Nothing,
      adjustments = [],
      comment = Nothing,
      exchangeRates = emptyExchangeRates,
      isUnrealized = False,
      isForecast = False
    }

day :: Integer -> Int -> Int -> Day
day = fromGregorian

-- Sample categories
expense :: Category
expense = mkCategory "Expense"

food :: Category
food = mkSubCategory "Food" expense

rent :: Category
rent = mkSubCategory "Rent" expense

income :: Category
income = mkCategory "Income"

salary :: Category
salary = mkSubCategory "Salary" income

--------------------------------------------------------------------------------
-- Tests
--------------------------------------------------------------------------------

main :: IO ()
main = do
  testMoneyAmount
  testCategory
  testTransaction
  testMatching
  testProcess
  testMultiCurrency
  putStrLn "\nAll tests passed."

testMoneyAmount :: IO ()
testMoneyAmount = do
  putStrLn "\n=== MoneyAmount ==="

  let a = MoneyAmount jpy 1000
      b = MoneyAmount jpy 500
      z = MoneyAmount usd 0

  assert "add same currency" $
    addAmounts a b == MoneyAmount jpy 1500

  assert "add with empty" $
    addAmounts emptyAmount a == a

  assert "subtract" $
    subtractAmounts a b == MoneyAmount jpy 500

  assert "negate" $
    negateAmount a == MoneyAmount jpy (-1000)

  assert "scale" $
    scaleAmount 2.0 a == MoneyAmount jpy 2000

  assert "zero amounts are equal regardless of currency" $
    MoneyAmount jpy 0 == z

  assert "sum single currency" $
    sumSingleCurrencyAmounts [a, b] == MoneyAmount jpy 1500

  assert "sum empty list" $
    sumSingleCurrencyAmounts [] == emptyAmount

testCategory :: IO ()
testCategory = do
  putStrLn "\n=== Category ==="

  assert "equality by label" $
    expense == mkCategory "Expense"

  assert "isUnder self" $
    isUnder food food

  assert "isUnder parent" $
    isUnder food expense

  assert "not isUnder unrelated" $
    not (isUnder food income)

  assert "isUnderAny" $
    isUnderAny food [income, expense]

  assert "depth of root" $
    categoryDepth expense == 0

  assert "depth of child" $
    categoryDepth food == 1

  assert "ancestorBy 0" $
    ancestorBy 0 food == food

  assert "ancestorBy 1" $
    ancestorBy 1 food == expense

testTransaction :: IO ()
testTransaction = do
  putStrLn "\n=== Transaction ==="

  let tx = mkTx MkTx {on = day 2025 1 15, desc = "Groceries", amount = -3000, cat = food, fromAcct = "SMBC"}

  assert "adjusted amount with no adjustments" $
    adjustedAmount tx == MoneyAmount jpy (-3000)

  let tx2 = addingAdjustment 500 tx
  assert "adjusted amount with adjustment" $
    adjustedAmount tx2 == MoneyAmount jpy (-2500)

  let tx3 = replacingCategory rent tx
  assert "replacing category" $
    tx3.category == rent

  let tx4 = replacingRelatedTo "Landlord" tx
  assert "replacing relatedTo" $
    tx4.relatedTo == Just "Landlord"

  -- synthesized transaction with amountIsRaw=False
  let synth =
        synthesizedTransaction
          defaultSynthesizedTx
            { synthDate = day 2025 3 1,
              synthDescription = "Synth",
              synthAmount = MoneyAmount jpy (-5000),
              synthCategory = expense,
              synthAccount = "Pseudo"
            }
  assert "synthesized: raw amount is zero" $
    synth.rawAmount.quantity == 0
  assert "synthesized: adjustment carries amount" $
    adjustedAmount synth == MoneyAmount jpy (-5000)

  -- synthesized transaction with amountIsRaw=True
  let synthRaw =
        synthesizedTransaction
          defaultSynthesizedTx
            { synthDate = day 2025 3 1,
              synthDescription = "SynthRaw",
              synthAmount = MoneyAmount jpy 10000,
              synthCategory = income,
              synthAccount = "Bank",
              synthAmountIsRaw = True
            }
  assert "synthesized raw: raw amount preserved" $
    synthRaw.rawAmount == MoneyAmount jpy 10000
  assert "synthesized raw: no adjustments" $
    null (synthRaw.adjustments)

testMatching :: IO ()
testMatching = do
  putStrLn "\n=== Matching ==="

  let tx1 = mkTx MkTx {on = day 2025 1 15, desc = "Groceries", amount = -3000, cat = food, fromAcct = "SMBC"}
      tx2 = mkTx MkTx {on = day 2025 2 20, desc = "Salary", amount = 500000, cat = salary, fromAcct = "Employer"}

  let foodMatch = mkMatching "is food" (\t -> t.category == food)
  assert "matching food" $
    foodMatch.fn tx1

  assert "not matching food" $
    not (foodMatch.fn tx2)

  assert "everything matches" $
    everything.fn tx1

  let incomeMatch = mkMatching "is income" (\t -> isUnder t.category income)
  let combined = satisfyAll [everything, incomeMatch]
  assert "satisfyAll" $
    combined.fn tx2

  assert "satisfyAll rejects" $
    not (combined.fn tx1)

  let anyMatch = satisfyAny [foodMatch, incomeMatch]
  assert "satisfyAny matches first" $
    anyMatch.fn tx1
  assert "satisfyAny matches second" $
    anyMatch.fn tx2

testProcess :: IO ()
testProcess = do
  putStrLn "\n=== Process ==="

  let tx1 = mkTx MkTx {on = day 2025 1 15, desc = "Groceries", amount = -3000, cat = food, fromAcct = "SMBC"}
      tx2 = mkTx MkTx {on = day 2025 2 20, desc = "Paycheck", amount = 500000, cat = salary, fromAcct = "Employer"}
      txs = [tx1, tx2]

  -- filterProc
  let foodMatch = mkMatching "is food" (\t -> t.category == food)
      filtered = (filterProc foodMatch).run txs
  assert "filterProc keeps matching" $
    length filtered == 1

  -- mapProc
  let renamer = mapProc "add suffix" (\t -> replacingDescription (t.description <> " (processed)") t)
      mapped = renamer.run txs
  assert "mapProc applies to all" $
    all (\t -> t.description /= "") mapped

  -- labelIfMatch
  let m = mkMatching "is salary" (\t -> isUnder t.category salary)
      proc = labelIfMatch m defaults {overrideRelatedTo = Just "Company"}
      labelled = proc.run txs
      salariedTx = head (filter (\t -> isUnder t.category salary) labelled)
  assert "labelIfMatch sets relatedTo" $
    salariedTx.relatedTo == Just "Company"

  -- GroupedProcess
  let gp =
        mkGroupedProcess
          "test pipeline"
          False
          [ filterProc everything,
            renamer
          ]
      result = runGroupedProcess gp txs
  assert "grouped process runs in sequence" $
    length result == 2

  -- labelAll
  let la = labelAll defaults {overrideCategory = Just rent}
      allRent = la.run txs
  assert "labelAll changes all categories" $
    all (\t -> t.category == rent) allRent

testMultiCurrency :: IO ()
testMultiCurrency = do
  putStrLn "\n=== MultiCurrency ==="

  let a = MoneyAmount jpy 1000
      b = MoneyAmount usd 50
      mca = sumCurrencyAmounts [a, b, a]

  assert "sum keeps separate currencies" $
    Map.size mca.quantities == 2

  assert "jpy total" $
    Map.lookup jpy mca.quantities == Just 2000

  assert "usd total" $
    Map.lookup usd mca.quantities == Just 50

  assert "empty equality" $
    emptyMultiCurrency == pruneZeroes (MultiCurrencyAmount (Map.singleton jpy 0))

  let negated = negateMultiCurrency mca
  assert "negation" $
    Map.lookup jpy negated.quantities == Just (-2000)

  -- totalRawAmount / totalAdjustedAmount
  let tx1 = mkTx MkTx {on = day 2025 1 1, desc = "A", amount = -1000, cat = expense, fromAcct = "X"}
      tx2 = mkTx MkTx {on = day 2025 1 2, desc = "B", amount = -2000, cat = expense, fromAcct = "X"}

  assert "totalRawAmount" $
    Map.lookup jpy (totalRawAmount [tx1, tx2]).quantities == Just (-3000)

  let tx3 = addingAdjustment 500 tx1
  assert "totalAdjustedAmount with adjustment" $
    Map.lookup jpy (totalAdjustedAmount [tx3, tx2]).quantities == Just (-2500)
