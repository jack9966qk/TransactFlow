from typing import Callable, List, Optional

from ..importers.amazonGiftCard import annotateAmazonGiftCardTransactions
from ..importers.amexJp import readAmexJpCsvFiles
from ..importers.amexUs import readAmexUsCsvFiles
from ..importers.diners import readDinersCsvFiles
from ..importers.jcb import readJcbCsvFiles
from ..importers.manualRecord import readManualRecordCsv
from ..importers.morganStanley import readMorganStanleyCsv
from ..importers.prestia import readPrestiaCsv
from ..importers.revolut import readRevolutCsv
from ..importers.sbi import readSBINetBankCSV
from ..importers.smbcCard import readSmbcCardCsvFiles
from ..importers.importer import addingCutoffTransactionTo


from ..base import *
from ..process import EVERYTHING, GroupedProcess, Process, labelIfMatch
from ..userConfig import ImporterConfig, MorganStanleyImportConfig


class ImporterProcess(Process):
    """
    Process responsible for:
        - introducing new transactions from a certain source
        - writing the account to the transactions
    """

    account: Optional[Account]
    readFromSource: Callable[[], List[Transaction]]

    def __init__(
        self,
        label: str,
        account: Optional[Account],
        readFromSource: Callable[[], List[Transaction]],
    ):
        super().__init__(label)
        self.account = account
        self.readFromSource = readFromSource

    def __call__(self, transactions: List[Transaction]) -> List[Transaction]:
        newTs = self.readFromSource()
        if self.account is not None:
            newTs = labelIfMatch(EVERYTHING, account=self.account)(newTs)
        return sortedByDate(transactions + newTs)


def _buildImporterProcesses(config: ImporterConfig) -> List[Process]:

    processes: List[Process] = []

    if (prestia := config.prestia) is not None:
        processes.append(ImporterProcess(
            label="Import SMBC Prestia",
            account=SMBC_PRESTIA,
            readFromSource=lambda p=prestia: readPrestiaCsv(
                p.csvPath, p.timestampPath),
        ))

    if (smbcCard := config.smbcCard) is not None:
        processes.append(ImporterProcess(
            label="Import SMBC Credit Card",
            account=SMBC_CREDIT_CARD,
            readFromSource=lambda s=smbcCard: concat(readSmbcCardCsvFiles(
                s.monthsDir, s.timestampPath)),
        ))

    if (jcb := config.jcb) is not None:
        processes.append(ImporterProcess(
            label="Import JCB Credit Card",
            account=JCB_CREDIT_CARD,
            readFromSource=lambda j=jcb: concat(readJcbCsvFiles(
                j.monthsDir, j.timestampPath)),
        ))

    if (diners := config.diners) is not None:
        processes.append(ImporterProcess(
            label="Import Diners",
            account=DINERS_CLUB,
            readFromSource=lambda d=diners: concat(readDinersCsvFiles(
                d.monthsDir, d.timestampPath)),
        ))

    if (amexJp := config.amexJp) is not None:
        processes.append(ImporterProcess(
            label="Import AMEX JP",
            account=AMEX_JP,
            readFromSource=lambda a=amexJp: concat(readAmexJpCsvFiles(
                a.convertedDir, a.timestampPath)),
        ))

    if (amexUs := config.amexUs) is not None:
        processes.append(ImporterProcess(
            label="Import AMEX US",
            account=AMEX_US,
            readFromSource=lambda a=amexUs: concat(readAmexUsCsvFiles(
                a.convertedDir, a.timestampPath)),
        ))

    if (revolut := config.revolut) is not None:
        processes.append(ImporterProcess(
            label="Import Revolut",
            account=REVOLUT,
            readFromSource=lambda r=revolut: readRevolutCsv(
                r.csvPath, r.timestampPath),
        ))

    if (sbi := config.sbi) is not None:
        processes.append(ImporterProcess(
            label="Import SBI Net Bank",
            account=SBI_NET_BANK,
            readFromSource=lambda s=sbi: readSBINetBankCSV(
                s.csvPath, s.timestampPath),
        ))

    if (manualRecord := config.manualRecord) is not None:
        processes.append(ImporterProcess(
            label="Import manual record",
            account=None,
            readFromSource=lambda m=manualRecord: readManualRecordCsv(m.csvPath),
        ))

    if (ms := config.morganStanley) is not None:
        processes.append(ImporterProcess(
            label="Import Morgan Stanley",
            account=MORGAN_STANLEY,
            readFromSource=lambda m=ms: readMorganStanleyCsv(m),
        ))

    if (agc := config.amazonGiftCard) is not None:
        processes.append(ImporterProcess(
            label="Import Amazon Gift Card",
            account=AMAZON_GIFT_CARD,
            readFromSource=lambda a=agc: annotateAmazonGiftCardTransactions(
                transactions=a.transactions,
                amazonGiftCardLastUpdateDate=a.lastUpdateDate,
                amazonPayAnnotations=a.payAnnotations,
                amazonPayAnnotationsLastUpdateDate=a.payAnnotationsLastUpdateDate,
            ),
        ))

    if (kyash := config.kyash) is not None:
        processes.append(ImporterProcess(
            label="Import Kyash",
            account=KYASH,
            readFromSource=lambda k=kyash: addingCutoffTransactionTo(
                k.transactions, date=k.lastUpdateDate, account=KYASH,
            ),
        ))

    return processes


def makeProcess(config: ImporterConfig) -> GroupedProcess:
    return GroupedProcess(label="Import", processes=_buildImporterProcesses(config))
