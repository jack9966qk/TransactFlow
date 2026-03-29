module TransactFlow.Process
  ( -- * Matching
    Matching (..),
    mkMatching,
    satisfyAll,
    satisfyAny,
    everything,

    -- * Process
    Process (..),
    mkProcess,
    GroupedProcess (..),
    mkGroupedProcess,
    runGroupedProcess,

    -- * Combinators
    filterProc,
    mapProc,
    LabelOverrides (..),
    defaults,
    labelIfMatch,
    labelAll,

    -- * Utilities
    takeMatched,
    takeFirstMatch,
  )
where

import Data.Text (Text)
import Data.Text qualified as T
import TransactFlow.Base

--------------------------------------------------------------------------------
-- Matching: a labelled predicate on transactions
--------------------------------------------------------------------------------

data Matching = Matching
  { label :: Text,
    fn :: Transaction -> Bool
  }

instance Show Matching where
  show m = "Matching: " <> T.unpack m.label

mkMatching :: Text -> (Transaction -> Bool) -> Matching
mkMatching = Matching

-- | A matching that requires all sub-matchings to hold.
satisfyAll :: [Matching] -> Matching
satisfyAll ms =
  Matching
    { label = "all of [" <> T.intercalate ", " (map (.label) ms) <> "]",
      fn = \t -> all (\m -> m.fn t) ms
    }

-- | A matching that requires at least one sub-matching to hold.
satisfyAny :: [Matching] -> Matching
satisfyAny ms =
  Matching
    { label = "any of [" <> T.intercalate ", " (map (.label) ms) <> "]",
      fn = \t -> any (\m -> m.fn t) ms
    }

-- | Matches every transaction.
everything :: Matching
everything = Matching "Everything" (const True)

--------------------------------------------------------------------------------
-- Process: a labelled transformation on a list of transactions
--------------------------------------------------------------------------------

data Process = Process
  { label :: Text,
    run :: [Transaction] -> [Transaction]
  }

instance Show Process where
  show p = "Process: " <> T.unpack p.label

mkProcess :: Text -> ([Transaction] -> [Transaction]) -> Process
mkProcess = Process

-- | A group of processes applied in sequence.
data GroupedProcess = GroupedProcess
  { label :: Text,
    atomic :: Bool,
    processes :: [Process]
  }
  deriving (Show)

mkGroupedProcess :: Text -> Bool -> [Process] -> GroupedProcess
mkGroupedProcess = GroupedProcess

-- | Run all processes in a group sequentially, threading the transaction list.
runGroupedProcess :: GroupedProcess -> [Transaction] -> [Transaction]
runGroupedProcess gp = foldl (flip (.run)) `flip` gp.processes

--------------------------------------------------------------------------------
-- Combinators
--------------------------------------------------------------------------------

-- | Keep only transactions that match.
filterProc :: Matching -> Process
filterProc m =
  Process
    { label = "Filter with " <> m.label,
      run = filter m.fn
    }

-- | Apply a mapping function to every transaction.
mapProc :: Text -> (Transaction -> Transaction) -> Process
mapProc lbl f =
  Process
    { label = "Map with " <> lbl,
      run = map f
    }

-- | Overrides to apply when a matching succeeds.
data LabelOverrides = LabelOverrides
  { overrideAccount :: Maybe Account,
    overrideCategory :: Maybe Category,
    overrideRelatedTo :: Maybe Account,
    overrideDescription :: Maybe Text,
    overrideComment :: Maybe Text,
    overrideExpected :: Maybe Int
  }
  deriving (Show)

-- | All-Nothing default; update the fields you need with record syntax.
defaults :: LabelOverrides
defaults = LabelOverrides Nothing Nothing Nothing Nothing Nothing Nothing

-- | The primary labelling combinator. For each transaction that matches,
-- apply the given overrides. If @overrideExpected@ is provided, asserts that
-- exactly that many transactions match.
labelIfMatch :: Matching -> LabelOverrides -> Process
labelIfMatch m ov =
  Process
    { label = "labelIfMatch(" <> m.label <> ")",
      run = \transactions ->
        let numMatching = length (filter m.fn transactions)
            passing = case ov.overrideExpected of
              Nothing -> numMatching > 0
              Just n -> numMatching == n
         in if not passing
              then
                error $
                  "labelIfMatch: expected match count failed for "
                    <> T.unpack m.label
                    <> " (got "
                    <> show numMatching
                    <> ")"
              else map applyLabel transactions
    }
  where
    applyLabel t
      | not (m.fn t) = t
      | otherwise =
          let t1 = maybe t (`replacingAccount` t) ov.overrideAccount
              t2 = maybe t1 (`replacingCategory` t1) ov.overrideCategory
              t3 = maybe t2 (`replacingRelatedTo` t2) ov.overrideRelatedTo
              t4 = maybe t3 (`replacingDescription` t3) ov.overrideDescription
              t5 = maybe t4 (`replacingComment` t4) ov.overrideComment
           in t5

-- | Label all transactions (matches everything).
labelAll :: LabelOverrides -> Process
labelAll = labelIfMatch everything

--------------------------------------------------------------------------------
-- Utilities
--------------------------------------------------------------------------------

-- | Partition transactions into matched and remaining, with an optional limit
-- on how many to match.
takeMatched :: Matching -> Maybe Int -> [Transaction] -> ([Transaction], [Transaction])
takeMatched m limit = go [] []
  where
    go matched remaining [] = (reverse matched, reverse remaining)
    go matched remaining (t : ts)
      | acceptMatching && m.fn t = go (t : matched) remaining ts
      | otherwise = go matched (t : remaining) ts
      where
        acceptMatching = case limit of
          Nothing -> True
          Just n -> length matched < n

-- | Take the first matching transaction, returning it and the rest.
takeFirstMatch :: Matching -> [Transaction] -> (Maybe Transaction, [Transaction])
takeFirstMatch m ts =
  let (matched, remaining) = takeMatched m (Just 1) ts
   in case matched of
        [] -> (Nothing, remaining)
        [t] -> (Just t, remaining)
        _ -> error "takeFirstMatch: impossible"
