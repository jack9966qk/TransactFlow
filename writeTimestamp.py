import sys
from pathlib import Path

import dateutil.parser

from transactflow.retrieval.common import writeLocalTimeString

if __name__ == "__main__":
    path = Path(sys.argv[1]).resolve()
    time = None
    if len(sys.argv) > 2:
        time = dateutil.parser.parse(sys.argv[2])
    writeLocalTimeString(path, time)
