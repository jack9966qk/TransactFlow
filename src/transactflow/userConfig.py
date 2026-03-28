from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class UserConfig:
    stockUnitTick: str
    morganStanleyCsvHeaderNumUnits: str
    morganStanleyVestedParsingShouldIgnore: Callable[[dict, str, int], bool]
    morganStanleyUnvestedParsingShouldIgnore: Callable[[dict, str, int], bool]
    morganStanleyWithdrawParsingShouldIgnore: Callable[[dict, str, int], bool]
    morganStanleyWithdrawTransform: Callable[[int, float, float], tuple[float, float, str]]


USER_CONFIG: Optional[UserConfig] = None

def setUserConfig(config: UserConfig):
    global USER_CONFIG
    USER_CONFIG = config

def forceReadUserConfig() -> UserConfig:
    config = USER_CONFIG
    assert(config is not None)
    return config
