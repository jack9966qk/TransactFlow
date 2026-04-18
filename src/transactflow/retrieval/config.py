from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Optional


class Browser(Enum):
    UC_CHROME = "uc_chrome"
    FIREFOX = "firefox"
    STOCK_CHROME = "stock_chrome"


def assertAbsolute(obj) -> None:
    """All `Path` fields of `obj` must be absolute (unambiguous)."""
    for f in fields(obj):
        value = getattr(obj, f.name)
        if isinstance(value, Path) and not value.is_absolute():
            raise ValueError(
                f"{type(obj).__name__}.{f.name} must be an absolute path, got: {value}"
            )


@dataclass(frozen=True)
class PrestiaRetrievalConfig:
    dataDir: Path
    timestampPath: Path
    expectDownloadedFilename: str
    userId: str

    def __post_init__(self) -> None:
        assertAbsolute(self)


@dataclass(frozen=True)
class SmbcCardRetrievalConfig:
    monthsDir: Path
    timestampPath: Path
    userId: str
    forLastNMonths: int = 3

    def __post_init__(self) -> None:
        assertAbsolute(self)


@dataclass(frozen=True)
class AmexRetrievalConfig:
    yearsDir: Path
    convertedDir: Path
    timestampPath: Path
    currentYear: int
    userId: str
    userDataDir: Path

    def __post_init__(self) -> None:
        assertAbsolute(self)


@dataclass(frozen=True)
class SuicaRetrievalConfig:
    dataDir: Path
    timestampPath: Path
    email: str

    def __post_init__(self) -> None:
        assertAbsolute(self)


@dataclass(frozen=True)
class RetrievalConfig:
    """All storage paths and per-institution configuration for retrieval.

    All `Path` fields must be absolute — relative paths depend on the caller's
    current working directory and are rejected.
    """
    downloadDir: Path
    credentialsDir: Path
    cookiesPath: Path
    browser: Browser = Browser.UC_CHROME
    # Required only when `browser == Browser.STOCK_CHROME`.
    chromeDriverPath: Optional[Path] = None
    prestia: Optional[PrestiaRetrievalConfig] = None
    smbcCard: Optional[SmbcCardRetrievalConfig] = None
    amexJp: Optional[AmexRetrievalConfig] = None
    amexUs: Optional[AmexRetrievalConfig] = None
    suica: Optional[SuicaRetrievalConfig] = None

    def __post_init__(self) -> None:
        assertAbsolute(self)
        if self.browser == Browser.STOCK_CHROME and self.chromeDriverPath is None:
            raise ValueError(
                "chromeDriverPath is required when browser == Browser.STOCK_CHROME"
            )
