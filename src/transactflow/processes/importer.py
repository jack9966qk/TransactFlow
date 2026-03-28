from typing import Callable, List, Sequence

from ..importers.amazonGiftCard import (
    AmazonPayAnnotation,
    annotateAmazonGiftCardTransactions,
)
from ..importers.amexJp import readAmexJpCsvFiles
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


def makeProcesses(
    prestiaCsvPath: Optional[str] = None,
    smbcCardCsvDir: Optional[str] = None,
    jcbCsvDir: Optional[str] = None,
    dinersCsvDir: Optional[str] = None,
    amexJpCsvDir: Optional[str] = None,
    revolutCsvPath: Optional[str] = None,
    sbiNetBankCsvPath: Optional[str] = None,
    manualRecordCsvPath: Optional[str] = None,
    morganStanleyEquityStatementPath: Optional[str] = None,
    morganStanleyEquityUnvestedPath: Optional[str] = None,
    morganStanleyWithdrawPath: Optional[str] = None,
    usdJpyRateAtDate: Optional[Dict[Date, float]] = None,
    amazonGiftCardTransactions: Optional[List[Transaction]] = None,
    amazonGiftCardLastUpdateDate: Optional[Date] = None,
    amazonPayAnnotations: Optional[List[AmazonPayAnnotation]] = None,
    amazonPayAnnotationsLastUpdateDate: Optional[Date] = None,
    kyashTransactions: Optional[List[Transaction]] = None,
    kyashLastUpdateDate: Optional[Date] = None,
) -> GroupedProcess:
    processes: Sequence[Process] = (
        (
            []
            if not prestiaCsvPath
            else [
                ImporterProcess(
                    label="Import SMBC Prestia",
                    account=SMBC_PRESTIA,
                    readFromSource=lambda: readPrestiaCsv(prestiaCsvPath),
                )
            ]
        )
        + (
            []
            if not smbcCardCsvDir
            else [
                ImporterProcess(
                    label="Import SMBC Credit Card",
                    account=SMBC_CREDIT_CARD,
                    readFromSource=lambda: concat(readSmbcCardCsvFiles()),
                )
            ]
        )
        + (
            []
            if not jcbCsvDir
            else [
                ImporterProcess(
                    label="Import JCB Credit Card",
                    account=JCB_CREDIT_CARD,
                    readFromSource=lambda: concat(readJcbCsvFiles()),
                ),
            ]
        )
        + (
            []
            if not dinersCsvDir
            else [
                ImporterProcess(
                    label="Import Diners",
                    account=DINERS_CLUB,
                    readFromSource=lambda: concat(readDinersCsvFiles()),
                )
            ]
        )
        + (
            []
            if not amexJpCsvDir
            else [
                ImporterProcess(
                    label="Import AMEX JP",
                    account=AMEX_JP,
                    readFromSource=lambda: concat(readAmexJpCsvFiles()),
                )
            ]
        )
        + (
            []
            if not revolutCsvPath
            else [
                ImporterProcess(
                    label="Import Revolut",
                    account=REVOLUT,
                    readFromSource=lambda: readRevolutCsv(revolutCsvPath),
                )
            ]
        )
        + (
            []
            if not sbiNetBankCsvPath
            else [
                ImporterProcess(
                    label="Import SBI Net Bank",
                    account=SBI_NET_BANK,
                    readFromSource=lambda: readSBINetBankCSV(sbiNetBankCsvPath),
                )
            ]
        )
        + (
            []
            if not manualRecordCsvPath
            else [
                ImporterProcess(
                    label="Import manual record",
                    account=None,
                    readFromSource=lambda: readManualRecordCsv(manualRecordCsvPath),
                ),
            ]
        )
        + (
            []
            if not (
                morganStanleyEquityStatementPath
                and morganStanleyEquityUnvestedPath
                and morganStanleyWithdrawPath
                and usdJpyRateAtDate
            )
            else [
                ImporterProcess(
                    label="Import Morgan Stanley",
                    account=MORGAN_STANLEY,
                    readFromSource=lambda: readMorganStanleyCsv(
                        statementFilePath=morganStanleyEquityStatementPath,
                        unvestedFilePath=morganStanleyEquityUnvestedPath,
                        includeUnvested=True,
                        withdrawReportFilePath=morganStanleyWithdrawPath,
                        usdJpyRateAtDate=usdJpyRateAtDate
                    ),
                )
            ]
        )
        + (
            []
            if not (
                amazonGiftCardTransactions
                and amazonGiftCardLastUpdateDate
                and amazonPayAnnotations
                and amazonPayAnnotationsLastUpdateDate
            )
            else [
                ImporterProcess(
                    label="Import Amazon Gift Card",
                    account=AMAZON_GIFT_CARD,
                    readFromSource=lambda: annotateAmazonGiftCardTransactions(
                        transactions=amazonGiftCardTransactions,
                        amazonGiftCardLastUpdateDate=amazonGiftCardLastUpdateDate,
                        amazonPayAnnotations=amazonPayAnnotations,
                        amazonPayAnnotationsLastUpdateDate=amazonPayAnnotationsLastUpdateDate,
                    ),
                ),
            ]
        )
        + (
            []
            if not (kyashTransactions and kyashLastUpdateDate)
            else [
                ImporterProcess(
                    label="Import Kyash",
                    account=KYASH,
                    readFromSource=lambda: addingCutoffTransactionTo(
                        kyashTransactions, date=kyashLastUpdateDate, account=KYASH
                    ),
                ),
            ]
        )
    )

    return GroupedProcess(label="Import", processes=list(processes))
