from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .base import Date, StockUnit, Transaction
from .processes.payslipAnnotationItem import PayslipAnnotationItem


# ---------------------------------------------------------------------------
# Importer path configs — one per data source
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrestiaPaths:
    csvPath: str
    timestampPath: str

@dataclass(frozen=True)
class SmbcCardPaths:
    monthsDir: str
    timestampPath: str

@dataclass(frozen=True)
class JcbPaths:
    monthsDir: str
    timestampPath: str

@dataclass(frozen=True)
class DinersPaths:
    monthsDir: str
    timestampPath: str

@dataclass(frozen=True)
class AmexJpPaths:
    convertedDir: str
    timestampPath: str

@dataclass(frozen=True)
class RevolutPaths:
    csvPath: str
    timestampPath: str

@dataclass(frozen=True)
class SbiPaths:
    csvPath: str
    timestampPath: str

@dataclass(frozen=True)
class ManualRecordPaths:
    csvPath: str

@dataclass(frozen=True)
class MorganStanleyImportConfig:
    stockUnit: StockUnit
    equityStatementPath: str
    equityUnvestedPath: str
    withdrawPath: str
    usdJpyRateAtDate: Dict[Date, float]
    csvHeaderNumUnits: str
    vestedParsingShouldIgnore: Callable[[dict, str, int], bool]
    unvestedParsingShouldIgnore: Callable[[dict, str, int], bool]
    withdrawParsingShouldIgnore: Callable[[dict, str, int], bool]
    withdrawTransform: Callable[[int, float, float], Tuple[float, float, str]]

@dataclass(frozen=True)
class AmazonGiftCardConfig:
    transactions: List[Transaction]
    lastUpdateDate: Date
    payAnnotations: List  # List[AmazonPayAnnotation] — avoid circular import
    payAnnotationsLastUpdateDate: Date

@dataclass(frozen=True)
class KyashConfig:
    transactions: List[Transaction]
    lastUpdateDate: Date


@dataclass(frozen=True)
class ImporterConfig:
    """All data source paths and configuration for the importer pipeline."""
    prestia: Optional[PrestiaPaths] = None
    smbcCard: Optional[SmbcCardPaths] = None
    jcb: Optional[JcbPaths] = None
    diners: Optional[DinersPaths] = None
    amexJp: Optional[AmexJpPaths] = None
    revolut: Optional[RevolutPaths] = None
    sbi: Optional[SbiPaths] = None
    manualRecord: Optional[ManualRecordPaths] = None
    morganStanley: Optional[MorganStanleyImportConfig] = None
    amazonGiftCard: Optional[AmazonGiftCardConfig] = None
    kyash: Optional[KyashConfig] = None


# ---------------------------------------------------------------------------
# Stock / Morgan Stanley config (parsing callbacks)
# ---------------------------------------------------------------------------

# TODO: Remove the global stock unit.
@dataclass(frozen=True)
class StockConfig:
    stockUnit: StockUnit


# ---------------------------------------------------------------------------
# Process config — user-supplied process lists
# ---------------------------------------------------------------------------

# Forward reference: Process is defined in process.py, but importing it would
# create a circular dependency (process.py → base.py ← userConfig.py).
# We use a plain List type at runtime; type checkers can use TYPE_CHECKING.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .process import Process

@dataclass(frozen=True)
class ProcessConfig:
    """User-supplied categorization and tax processes."""
    simpleProcess: Optional["Process"] = None
    complexProcess: Optional["Process"] = None
    taxProcess: Optional["Process"] = None
    payslipAnnotations: Optional[List[PayslipAnnotationItem]] = None


# ---------------------------------------------------------------------------
# Forecast config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ForecastConfig:
    targetYear: int


# ---------------------------------------------------------------------------
# Top-level UserConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UserConfig:
    stock: Optional[StockConfig] = None
    importers: Optional[ImporterConfig] = None
    processes: Optional[ProcessConfig] = None
    forecast: Optional[ForecastConfig] = None


USER_CONFIG: Optional[UserConfig] = None

def setUserConfig(config: UserConfig):
    global USER_CONFIG
    USER_CONFIG = config

def forceReadUserConfig() -> UserConfig:
    config = USER_CONFIG
    assert config is not None, "UserConfig has not been set. Call setUserConfig() first."
    return config
