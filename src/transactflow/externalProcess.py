"""Conversions between native Matching/Mapping/Process types and their protobuf
ExternalMatching/ExternalMapping/ExternalProcess counterparts."""

from typing import Dict, List, Optional

from .base import Account, Category, Date, MoneyAmount
from .externalTransaction import _categoryFromProto, _categoryToProto
from .process import (
    EVERYTHING,
    FunctionProcess,
    GroupedProcess,
    LabelledFunctionalMapping,
    LabelledFunctionalMatching,
    Mapping,
    Matching,
    Process,
    filterProc,
    funcMapping,
    labelIfMatch,
    mapProc,
    matching,
    satisfyAll,
    satisfyAny,
    sortByDate,
    sortByDateAndMore,
    writeCatIf,
)
from .proto_gen import transactflow_pb2 as pb


# ---------------------------------------------------------------------------
# Named-instance registries
#
# Known functional matchings/mappings/processes that have no serialisable
# parameters are stored by name.  Both directions (to-proto, from-proto) use
# the same registry so that the mapping is always consistent.
# ---------------------------------------------------------------------------

# Matching name -> instance.  Populated at module level; callers may extend.
_NAMED_MATCHINGS: Dict[str, Matching] = {}

# Process name -> instance.
_NAMED_PROCESSES: Dict[str, Process] = {}

# Mapping name -> instance.
_NAMED_MAPPINGS: Dict[str, Mapping] = {}

# Reverse lookups (id -> name) built lazily.
_MATCHING_ID_TO_NAME: Dict[int, str] = {}
_PROCESS_ID_TO_NAME: Dict[int, str] = {}
_MAPPING_ID_TO_NAME: Dict[int, str] = {}


def _rebuildReverseLookups() -> None:
    _MATCHING_ID_TO_NAME.clear()
    _PROCESS_ID_TO_NAME.clear()
    _MAPPING_ID_TO_NAME.clear()
    for name, inst in _NAMED_MATCHINGS.items():
        _MATCHING_ID_TO_NAME[id(inst)] = name
    for name, inst in _NAMED_PROCESSES.items():
        _PROCESS_ID_TO_NAME[id(inst)] = name
    for name, inst in _NAMED_MAPPINGS.items():
        _MAPPING_ID_TO_NAME[id(inst)] = name


def registerNamedMatching(name: str, inst: Matching) -> None:
    _NAMED_MATCHINGS[name] = inst
    _MATCHING_ID_TO_NAME[id(inst)] = name


def registerNamedProcess(name: str, inst: Process) -> None:
    _NAMED_PROCESSES[name] = inst
    _PROCESS_ID_TO_NAME[id(inst)] = name


def registerNamedMapping(name: str, inst: Mapping) -> None:
    _NAMED_MAPPINGS[name] = inst
    _MAPPING_ID_TO_NAME[id(inst)] = name


# Register built-in named instances from process.py.
def _registerBuiltins() -> None:
    from .process import (
        isDailyShopping,
        isMajorShopping,
        isSalary,
        labelGeneralExpenseDestination,
        labelNotReallyIncomeIfUncategorizedIncome,
        labelSalaryIncome,
        moveSalaryToFirstOfDay,
        relabelShoppingAsDaily,
        relabelShoppingAsMajor,
    )

    registerNamedMatching("isSalary", isSalary)
    registerNamedMatching("isDailyShopping", isDailyShopping)
    registerNamedMatching("isMajorShopping", isMajorShopping)
    registerNamedMatching("EVERYTHING", EVERYTHING)

    registerNamedProcess("labelSalaryIncome", labelSalaryIncome)
    registerNamedProcess(
        "labelNotReallyIncomeIfUncategorizedIncome",
        labelNotReallyIncomeIfUncategorizedIncome,
    )
    registerNamedProcess(
        "labelGeneralExpenseDestination", labelGeneralExpenseDestination
    )
    registerNamedProcess("relabelShoppingAsDaily", relabelShoppingAsDaily)
    registerNamedProcess("relabelShoppingAsMajor", relabelShoppingAsMajor)
    registerNamedProcess("sortByDate", sortByDate)
    registerNamedProcess("sortByDateAndMore", sortByDateAndMore)
    registerNamedProcess("moveSalaryToFirstOfDay", moveSalaryToFirstOfDay)


_registerBuiltins()


# ---------------------------------------------------------------------------
# Matching: to / from proto
# ---------------------------------------------------------------------------

def _dateToProto(d: Date) -> pb.Date:
    return pb.Date(year=d.year, month=d.month, day=d.day)


def _dateFromProto(d: pb.Date) -> Date:
    return Date(year=d.year, month=d.month, day=d.day)


def _matchingParamsToProto(m: LabelledFunctionalMatching) -> Optional[pb.MatchingParams]:
    """Try to reverse-engineer a parametric matching back to MatchingParams.

    This only works for matchings created via the ``matching(...)`` constructor
    whose label is the ``argsDesc`` of its keyword arguments.  If the label
    doesn't look parametric we return ``None``.
    """
    # The label produced by matching() looks like "account=SMBC Prestia, descSubstr=foo".
    # We parse key=value pairs from it.
    label = m.label
    if not label or "=" not in label:
        return None

    kwargs: dict = {}
    # Split on ", " but be careful with values that may contain commas.
    # The matching() function uses argsDesc which joins with ", " and uses
    # "key=value" pairs. We parse greedily.
    parts = label.split(", ")
    # Rejoin parts that don't contain "=" with the previous part (value contained a comma).
    merged: List[str] = []
    for part in parts:
        if "=" in part and (not merged or "=" in merged[-1]):
            merged.append(part)
        else:
            if merged:
                merged[-1] += ", " + part
            else:
                merged.append(part)

    for pair in merged:
        eqIdx = pair.index("=")
        key = pair[:eqIdx].strip()
        val = pair[eqIdx + 1:].strip()

        if key == "account":
            kwargs["account"] = val
        elif key == "year":
            kwargs["year"] = int(val)
        elif key == "month":
            kwargs["month"] = int(val)
        elif key == "day":
            kwargs["day"] = int(val)
        elif key == "exactCategory":
            # Category label is stored as repr "<Category: Foo>" — extract the label.
            catLabel = val
            if catLabel.startswith("<Category: ") and catLabel.endswith(">"):
                catLabel = catLabel[len("<Category: "):-1]
            kwargs["exact_category"] = _categoryToProto(Category(label=catLabel))
        elif key == "exactDesc":
            kwargs["exact_desc"] = val
        elif key == "descSubstr":
            kwargs["desc_substr"] = val
        elif key == "anyDescSubStr":
            # Stored as repr of a list: "['a', 'b']"
            kwargs["any_desc_sub_str"] = _parseStrList(val)
        elif key == "anyDescRegex":
            kwargs["any_desc_regex"] = _parseStrList(val)
        elif key == "normalizeDesc":
            kwargs["normalize_desc"] = val == "True"
        elif key == "descRegexIgnoreCase":
            kwargs["desc_regex_ignore_case"] = val == "True"
        elif key == "amountPosNegIs":
            kwargs["amount_pos_neg_is"] = val
        elif key == "quantity":
            kwargs["quantity"] = float(val)
        elif key == "adjustedQuantity":
            kwargs["adjusted_quantity"] = float(val)
        elif key == "dateFrom":
            kwargs["date_from"] = _parseDateToProto(val)
        elif key == "dateUntil":
            kwargs["date_until"] = _parseDateToProto(val)
        elif key == "date":
            kwargs["date"] = val
        elif key == "originalFormat":
            kwargs["original_format"] = val
        elif key == "breakpointOnTransaction":
            # Cannot serialise; skip.
            pass
        else:
            return None  # Unknown parameter — cannot round-trip.

    return pb.MatchingParams(**kwargs)


def _parseStrList(s: str) -> List[str]:
    """Parse a Python repr of a string list, e.g. \"['a', 'b']\"."""
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    items: List[str] = []
    for item in s.split(","):
        item = item.strip().strip("'\"")
        if item:
            items.append(item)
    return items


def _parseDateToProto(s: str) -> pb.Date:
    """Parse a date string like 'datetime.date(2024, 1, 15)' or '2024-01-15'."""
    s = s.strip()
    if s.startswith("datetime.date("):
        inner = s[len("datetime.date("):-1]
        parts = [int(p.strip()) for p in inner.split(",")]
        return pb.Date(year=parts[0], month=parts[1], day=parts[2])
    parts = s.split("-")
    return pb.Date(year=int(parts[0]), month=int(parts[1]), day=int(parts[2]))


def matchingToProto(m: Matching) -> pb.ExternalMatching:
    """Convert a native Matching to a protobuf ExternalMatching."""
    # Check named registry first.
    name = _MATCHING_ID_TO_NAME.get(id(m))
    if name is not None:
        return pb.ExternalMatching(label=m.label, named=name)

    # Check structural patterns via label.
    label = m.label

    if label == "Everything":
        return pb.ExternalMatching(label=label, everything=True)

    if label.startswith("Satisfy all of f"):
        raise ValueError(
            f"Cannot serialise satisfyAll matching by label alone: {label!r}. "
            "Register it as a named matching or construct it from sub-matchings."
        )
    if label.startswith("Satisfy any of f"):
        raise ValueError(
            f"Cannot serialise satisfyAny matching by label alone: {label!r}. "
            "Register it as a named matching or construct it from sub-matchings."
        )

    # Try parametric parsing.
    if isinstance(m, LabelledFunctionalMatching):
        params = _matchingParamsToProto(m)
        if params is not None:
            return pb.ExternalMatching(label=label, parametric=params)

    raise ValueError(
        f"Cannot convert matching to proto: {m!r}. "
        "Register it as a named matching via registerNamedMatching()."
    )


def matchingToProtoComposite(
    m: Matching, *, subMatchings: Optional[List[Matching]] = None
) -> pb.ExternalMatching:
    """Convert a composite matching (satisfyAll/satisfyAny) when sub-matchings
    are known by the caller."""
    label = m.label
    if subMatchings is not None:
        protoSubs = [matchingToProto(s) for s in subMatchings]
        if label.startswith("Satisfy all"):
            return pb.ExternalMatching(
                label=label,
                satisfy_all=pb.MatchingList(matchings=protoSubs),
            )
        if label.startswith("Satisfy any"):
            return pb.ExternalMatching(
                label=label,
                satisfy_any=pb.MatchingList(matchings=protoSubs),
            )
    return matchingToProto(m)


def matchingFromProto(em: pb.ExternalMatching) -> Matching:
    """Convert a protobuf ExternalMatching to a native Matching."""
    variant = em.WhichOneof("type")

    if variant == "everything":
        return EVERYTHING

    if variant == "named":
        name = em.named
        inst = _NAMED_MATCHINGS.get(name)
        if inst is None:
            raise ValueError(f"Unknown named matching: {name!r}")
        return inst

    if variant == "parametric":
        return _matchingParamsFromProto(em.parametric, em.label)

    if variant == "satisfy_all":
        subs = [matchingFromProto(s) for s in em.satisfy_all.matchings]
        return satisfyAll(subs)

    if variant == "satisfy_any":
        subs = [matchingFromProto(s) for s in em.satisfy_any.matchings]
        return satisfyAny(subs)

    raise ValueError(f"ExternalMatching has no type set: {em!r}")


def _matchingParamsFromProto(mp: pb.MatchingParams, label: str) -> Matching:
    """Reconstruct a parametric matching from MatchingParams."""
    kwargs: dict = {}

    if mp.HasField("account"):
        kwargs["account"] = mp.account
    if mp.HasField("year"):
        kwargs["year"] = mp.year
    if mp.HasField("month"):
        kwargs["month"] = mp.month
    if mp.HasField("day"):
        kwargs["day"] = mp.day
    if mp.HasField("exact_category"):
        kwargs["exactCategory"] = _categoryFromProto(mp.exact_category)
    if mp.HasField("exact_desc"):
        kwargs["exactDesc"] = mp.exact_desc
    if mp.HasField("desc_substr"):
        kwargs["descSubstr"] = mp.desc_substr
    if len(mp.any_desc_sub_str) > 0:
        kwargs["anyDescSubStr"] = list(mp.any_desc_sub_str)
    if len(mp.any_desc_regex) > 0:
        kwargs["anyDescRegex"] = list(mp.any_desc_regex)
    if mp.normalize_desc:
        kwargs["normalizeDesc"] = True
    if mp.desc_regex_ignore_case:
        kwargs["descRegexIgnoreCase"] = True
    if mp.HasField("amount_pos_neg_is"):
        kwargs["amountPosNegIs"] = mp.amount_pos_neg_is
    if mp.HasField("quantity"):
        kwargs["quantity"] = mp.quantity
    if mp.HasField("adjusted_quantity"):
        kwargs["adjustedQuantity"] = mp.adjusted_quantity
    if mp.HasField("date_from"):
        kwargs["dateFrom"] = _dateFromProto(mp.date_from)
    if mp.HasField("date_until"):
        kwargs["dateUntil"] = _dateFromProto(mp.date_until)
    if mp.HasField("date"):
        kwargs["date"] = mp.date
    if mp.HasField("original_format"):
        kwargs["originalFormat"] = mp.original_format

    return matching(**kwargs)


# ---------------------------------------------------------------------------
# Mapping: to / from proto
# ---------------------------------------------------------------------------

def mappingToProto(m: Mapping) -> pb.ExternalMapping:
    """Convert a native Mapping to a protobuf ExternalMapping."""
    name = _MAPPING_ID_TO_NAME.get(id(m))
    if name is not None:
        return pb.ExternalMapping(label=m.label, named=name)

    # Try to detect writeCatIf pattern from label.
    if isinstance(m, LabelledFunctionalMapping) and m.label.startswith("write cat if "):
        raise ValueError(
            f"Cannot serialise writeCatIf mapping without knowing the sub-matching and "
            f"category. Use mappingToProtoWriteCatIf() instead, or register as named."
        )

    raise ValueError(
        f"Cannot convert mapping to proto: {m!r}. "
        "Register it as a named mapping via registerNamedMapping()."
    )


def mappingToProtoWriteCatIf(
    m: Mapping, innerMatching: Matching, category: Category
) -> pb.ExternalMapping:
    """Convert a writeCatIf mapping when the matching and category are known."""
    return pb.ExternalMapping(
        label=m.label,
        write_cat_if=pb.WriteCatIfParams(
            matching=matchingToProto(innerMatching),
            category=_categoryToProto(category),
        ),
    )


def mappingFromProto(em: pb.ExternalMapping) -> Mapping:
    """Convert a protobuf ExternalMapping to a native Mapping."""
    variant = em.WhichOneof("type")

    if variant == "named":
        name = em.named
        inst = _NAMED_MAPPINGS.get(name)
        if inst is None:
            raise ValueError(f"Unknown named mapping: {name!r}")
        return inst

    if variant == "write_cat_if":
        innerMatching = matchingFromProto(em.write_cat_if.matching)
        category = _categoryFromProto(em.write_cat_if.category)
        return writeCatIf(innerMatching, category)

    raise ValueError(f"ExternalMapping has no type set: {em!r}")


# ---------------------------------------------------------------------------
# Process: to / from proto
# ---------------------------------------------------------------------------

def processToProto(p: Process) -> pb.ExternalProcess:
    """Convert a native Process to a protobuf ExternalProcess."""
    # Check named registry first.
    name = _PROCESS_ID_TO_NAME.get(id(p))
    if name is not None:
        return pb.ExternalProcess(label=p.label, named=name)

    # sortByDate / sortByDateAndMore by label (they are FunctionProcess instances).
    if isinstance(p, FunctionProcess):
        if p.label == "sortByDate":
            return pb.ExternalProcess(label=p.label, sort_by_date=True)
        if p.label == "sortByDateAndMore":
            return pb.ExternalProcess(label=p.label, sort_by_date_and_more=True)

    # GroupedProcess
    if isinstance(p, GroupedProcess):
        protoProcesses = [processToProto(sub) for sub in p.processes]
        return pb.ExternalProcess(
            label=p.label,
            grouped=pb.ExternalProcessList(
                processes=protoProcesses, atomic=p.atomic
            ),
        )

    raise ValueError(
        f"Cannot convert process to proto: {p!r}. "
        "Register it as a named process via registerNamedProcess()."
    )


def processToProtoLabelIfMatch(
    p: Process,
    innerMatching: Matching,
    account: Optional[Account] = None,
    category: Optional[Category] = None,
    relatedTo: Optional[Account] = None,
    description: Optional[str] = None,
    comment: Optional[str] = None,
    expected: Optional[int] = None,
) -> pb.ExternalProcess:
    """Convert a labelIfMatch process when the matching and overrides are known."""
    overridesKwargs: dict = {}
    if account is not None:
        overridesKwargs["account"] = account
    if category is not None:
        overridesKwargs["category"] = _categoryToProto(category)
    if relatedTo is not None:
        overridesKwargs["related_to"] = relatedTo
    if description is not None:
        overridesKwargs["description"] = description
    if comment is not None:
        overridesKwargs["comment"] = comment
    if expected is not None:
        overridesKwargs["expected"] = expected
    return pb.ExternalProcess(
        label=p.label,
        label_if_match=pb.LabelIfMatchParams(
            matching=matchingToProto(innerMatching),
            overrides=pb.LabelOverrides(**overridesKwargs),
        ),
    )


def processToProtoFilter(p: Process, innerMatching: Matching) -> pb.ExternalProcess:
    """Convert a filterProc process when the matching is known."""
    return pb.ExternalProcess(
        label=p.label,
        filter=matchingToProto(innerMatching),
    )


def processToProtoMap(p: Process, innerMapping: Mapping) -> pb.ExternalProcess:
    """Convert a mapProc process when the mapping is known."""
    return pb.ExternalProcess(
        label=p.label,
        map=mappingToProto(innerMapping),
    )


def processFromProto(ep: pb.ExternalProcess) -> Process:
    """Convert a protobuf ExternalProcess to a native Process."""
    variant = ep.WhichOneof("type")

    if variant == "named":
        name = ep.named
        inst = _NAMED_PROCESSES.get(name)
        if inst is None:
            raise ValueError(f"Unknown named process: {name!r}")
        return inst

    if variant == "sort_by_date":
        return sortByDate

    if variant == "sort_by_date_and_more":
        return sortByDateAndMore

    if variant == "label_if_match":
        lim = ep.label_if_match
        m = matchingFromProto(lim.matching)
        ov = lim.overrides
        kwargs: dict = {}
        if ov.HasField("account"):
            kwargs["account"] = ov.account
        if ov.HasField("category"):
            kwargs["category"] = _categoryFromProto(ov.category)
        if ov.HasField("related_to"):
            kwargs["relatedTo"] = ov.related_to
        if ov.HasField("description"):
            kwargs["description"] = ov.description
        if ov.HasField("comment"):
            kwargs["comment"] = ov.comment
        if ov.HasField("expected"):
            kwargs["expected"] = ov.expected
        return labelIfMatch(m, **kwargs)

    if variant == "filter":
        m = matchingFromProto(ep.filter)
        return filterProc(m)

    if variant == "map":
        mapping = mappingFromProto(ep.map)
        return mapProc(mapping)

    if variant == "grouped":
        gl = ep.grouped
        subProcesses = [processFromProto(sub) for sub in gl.processes]
        return GroupedProcess(
            label=ep.label, atomic=gl.atomic, processes=subProcesses
        )

    raise ValueError(f"ExternalProcess has no type set: {ep!r}")
