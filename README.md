# TransactFlow

A personal accounting system designed to be:

* Private: completely local storage of credentials, transactions data, and analysis results
* Customizable: easily compose processes or build new ones that transforms the transactions
* Automatic: save manual work of data retrieval, tax calculations and more

## Usage

### Installation

TransactFlow requires Python 3.14+. Install directly from GitHub:

```bash
pip install git+https://github.com/jack9966qk/TransactFlow.git@0.1.0
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add git+https://github.com/jack9966qk/TransactFlow.git --tag 0.1.0
```

### Example

Here is a short example:

```python
from transactflow.base import *
from transactflow.userConfig import *
from transactflow.analysis import *
from transactflow.process import *
import transactflow.processes.runAll as runner

config = UserConfig(
    importers=ImporterConfig(
        revolut=RevolutPaths(
            csvPath="/path/to/revolut/all.csv",
            timestampPath="/path/to/revolut/last_update_time",
        ),
        amexJp=AmexJpPaths(
            convertedDir="/path/to/amex-jp/converted_years/",
            timestampPath="/path/to/amex-jp/last_update_time",
        ),
    ),
    processes=ProcessConfig(
        simpleProcess=GroupedProcess(processes=[
            labelIfMatch(
                matching(account=REVOLUT, descSubstr="salary"),
                category=SALARY,
                relatedTo=EMPLOYER
            ),
            labelIfMatch(
                matching(account=AMEX_JP, descSubstr="Amazon"),
                category=SHOPPING,
            ),
        ])
    )
)
setUserConfig(config)
print(netWorthReport(runner.run()))
```

## Design

### Transaction

Transaction is the basic unit of financial record. A list of transactions represent the single source of truth of the financial state. Transactions are meant to be immutable, so that modifications to a transaction are performed by creating a new version of the transaction. Specifically, modifications of amounts are tracked so that the effects of the system can be understood more easily.

### Process

Process is a generic building block that transforms a list of transactions into another. Processes can be chained and grouped. The intention is that all operations on transactions should be defined as processes. Examples include:

* Importer processes that adds transactions from some data source
* Labeling processes that assigns categories to transactions based on description or account
* Tax processes that calculate tax estimations and distribute the amounts

### Analysis module

A collection of tools that help present the financial state, either as a data class (`AnalysisProvider`) or an HTTP server (`AnalysisServer`). They are responsible for generating derivative data from the transactions, such as totals by account or currency.

This repository also includes a Python notebook for visualizations.

### Retrieval module

A collection of automation tools to help retrieving financial records automatically, supporting various institutions.

## Experimental work

There is ongoing work with a Haskell implementation and protobuf definitions. In the future, the project might migrate to Haskell, and user configruations might be specified in a language agonstic way.
