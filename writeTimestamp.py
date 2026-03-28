from transactflow.retrieval.common import writeLocalTimeString
import dateutil.parser
import sys

if __name__ == "__main__":
    path = sys.argv[1]
    time = None
    if len(sys.argv) > 2:
        time = dateutil.parser.parse(sys.argv[2])
    writeLocalTimeString(path, time)
