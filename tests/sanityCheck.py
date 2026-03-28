from transactflow.processes.runAll import run
from transactflow.analysis import AnalysisProvider
from transactflow.base import splitIntoTimeSectionsBySalaryIncome

# Initialize analysis provider.
trans = run()
groups, _ = splitIntoTimeSectionsBySalaryIncome(trans)
provider = AnalysisProvider(trans, groups)
