module TransactFlow.ExternalProcess
  ( -- * Matching conversion
    matchingToProto,
    matchingFromProto,

    -- * Mapping conversion
    mappingToProto,
    mappingFromProto,

    -- * Process conversion
    processToProto,
    processFromProto,
  )
where

import Data.ProtoLens (defMessage)
import Data.Text (Text)
import Data.Text qualified as T
import Lens.Family2 (view, (&), (.~))
import Proto.Transactflow qualified as P
import Proto.Transactflow_Fields qualified as F
import TransactFlow.Base
import TransactFlow.ExternalTransaction (categoryFromProto)
import TransactFlow.Process

--------------------------------------------------------------------------------
-- Matching: to / from proto
--------------------------------------------------------------------------------

matchingToProto :: Matching -> P.ExternalMatching
matchingToProto m
  | m.label == "Everything" =
      defMessage
        & F.label .~ m.label
        & F.everything .~ True
  | otherwise =
      error $
        "matchingToProto: cannot convert matching: "
          <> T.unpack m.label
          <> ". ExternalProcess conversion is not yet implemented in Haskell."

matchingFromProto :: P.ExternalMatching -> Matching
matchingFromProto em =
  case view F.maybe'type' em of
    Just (P.ExternalMatching'Everything _) -> everything
    Just (P.ExternalMatching'Named name) ->
      error $
        "matchingFromProto: named matching not implemented: " <> T.unpack name
    Just (P.ExternalMatching'Parametric _mp) ->
      error "matchingFromProto: parametric matching not yet implemented in Haskell"
    Just (P.ExternalMatching'SatisfyAll ml) ->
      satisfyAll (map matchingFromProto (view F.matchings ml))
    Just (P.ExternalMatching'SatisfyAny ml) ->
      satisfyAny (map matchingFromProto (view F.matchings ml))
    Nothing ->
      error "matchingFromProto: ExternalMatching has no type set"

--------------------------------------------------------------------------------
-- Mapping: to / from proto
--------------------------------------------------------------------------------

mappingToProto :: Text -> (Transaction -> Transaction) -> P.ExternalMapping
mappingToProto _lbl _f =
  error "mappingToProto: not yet implemented in Haskell"

mappingFromProto :: P.ExternalMapping -> (Text, Transaction -> Transaction)
mappingFromProto em =
  case view F.maybe'type' em of
    Just (P.ExternalMapping'WriteCatIf wc) ->
      let innerM = matchingFromProto (view F.matching wc)
          cat = categoryFromProto (view F.category wc)
          lbl = view F.label em
          mapFn t
            | innerM.fn t = replacingCategory cat t
            | otherwise = t
       in (lbl, mapFn)
    Just (P.ExternalMapping'Named name) ->
      error $ "mappingFromProto: named mapping not implemented: " <> T.unpack name
    Nothing ->
      error "mappingFromProto: ExternalMapping has no type set"

--------------------------------------------------------------------------------
-- Process: to / from proto
--------------------------------------------------------------------------------

processToProto :: Process -> P.ExternalProcess
processToProto _p =
  error "processToProto: not yet implemented in Haskell"

processFromProto :: P.ExternalProcess -> Process
processFromProto ep =
  case view F.maybe'type' ep of
    Just (P.ExternalProcess'LabelIfMatch lim) ->
      let m = matchingFromProto (view F.matching lim)
          ov = view F.overrides lim
          ovs =
            defaults
              { overrideAccount = view F.maybe'account ov,
                overrideCategory = fmap categoryFromProto (view F.maybe'category ov),
                overrideRelatedTo = view F.maybe'relatedTo ov,
                overrideDescription = view F.maybe'description ov,
                overrideComment = view F.maybe'comment ov,
                overrideExpected = fmap fromIntegral (view F.maybe'expected ov)
              }
       in labelIfMatch m ovs
    Just (P.ExternalProcess'Filter em) ->
      filterProc (matchingFromProto em)
    Just (P.ExternalProcess'Map em) ->
      let (lbl, mapFn) = mappingFromProto em
       in mapProc lbl mapFn
    Just (P.ExternalProcess'Grouped gl) ->
      let subProcesses = map processFromProto (view F.processes gl)
          lbl = view F.label ep
          isAtomic = view F.atomic gl
       in mkProcess lbl (runGroupedProcess (mkGroupedProcess lbl isAtomic subProcesses))
    Just (P.ExternalProcess'SortByDate _) ->
      mkProcess "sortByDate" (map id)  -- placeholder: proper sortByDate not yet exposed
    Just (P.ExternalProcess'SortByDateAndMore _) ->
      mkProcess "sortByDateAndMore" (map id)  -- placeholder
    Just (P.ExternalProcess'Named name) ->
      error $ "processFromProto: named process not implemented: " <> T.unpack name
    Nothing ->
      error "processFromProto: ExternalProcess has no type set"
