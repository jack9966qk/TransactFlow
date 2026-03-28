from processes.runAll import run
from analysis import AnalysisProvider
from base import splitIntoTimeSectionsBySalaryIncome

# Initialize analysis provider.
trans = run()
groups, _ = splitIntoTimeSectionsBySalaryIncome(trans)
provider = AnalysisProvider(trans, groups)
