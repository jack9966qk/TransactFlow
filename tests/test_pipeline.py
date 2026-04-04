"""Tests for the full processing pipeline using mock data."""

import os
from datetime import date

from transactflow.base import (
    EXPENSE, INCOME, SALARY, SMBC_PRESTIA, REVOLUT,
    JPY, MoneyAmount, Transaction, sortedByDate,
    GENERAL_EXPENSE_DESTINATION,
)
from transactflow.process import GroupedProcess
from transactflow.processes.importer import ImporterProcess
from transactflow.userConfig import (
    ImporterConfig, PrestiaPaths, RevolutPaths, StockConfig, ProcessConfig,
    ForecastConfig, UserConfig, setUserConfig,
)
from transactflow.importers.prestia import readPrestiaCsv
from transactflow.importers.revolut import readRevolutCsv

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DATA_DIR = os.path.join(TESTS_DIR, "data")


def _prestia_timestamp_path():
    return os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "last_update_time")


def _revolut_timestamp_path():
    return os.path.join(TEST_DATA_DIR, "rawTransactions", "revolut", "last_update_time")


def _dummy_stock_config():
    return StockConfig(
        stockUnitTick="DUMMY"
    )


class TestPipelineWithMockData:
    def test_import_only(self):
        """Test that the import step loads transactions from mock CSV."""
        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")
        ts_path = _prestia_timestamp_path()

        importer = ImporterProcess(
            label="Import SMBC Prestia",
            account=SMBC_PRESTIA,
            readFromSource=lambda: readPrestiaCsv(csv_path, ts_path),
        )
        transactions = importer([])

        assert len(transactions) > 0
        assert all(t.account == SMBC_PRESTIA for t in transactions)
        dates = [t.date for t in transactions]
        assert dates == sorted(dates)

    def test_import_and_simple(self):
        """Test import + simple categorization.

        Note: The default simple.py only labels salary when relatedTo == EMPLOYER,
        which requires prior labelling by user-specific rules. With raw prestia
        data, income transactions without relatedTo=EMPLOYER become EXCLUDED_INCOME.
        """
        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")
        ts_path = _prestia_timestamp_path()

        setUserConfig(UserConfig(
            stock=_dummy_stock_config(),
            importers=ImporterConfig(
                prestia=PrestiaPaths(csvPath=csv_path, timestampPath=ts_path),
            ),
            processes=ProcessConfig(),
            forecast=ForecastConfig(targetYear=2025),
        ))

        from transactflow.processes.simple import process as simple_process
        # Force re-resolve since config changed
        simple_process._resolved = False

        importer = ImporterProcess(
            label="Import SMBC Prestia",
            account=SMBC_PRESTIA,
            readFromSource=lambda: readPrestiaCsv(csv_path, ts_path),
        )
        pipeline = GroupedProcess(label="Test pipeline", processes=[
            importer,
            simple_process,
        ])
        transactions = pipeline([])

        assert len(transactions) > 0

    def test_import_multiple_sources(self):
        """Test importing from multiple sources at once."""
        prestia_csv = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")
        prestia_ts = _prestia_timestamp_path()
        revolut_csv = os.path.join(TEST_DATA_DIR, "rawTransactions", "revolut", "transactions.csv")
        revolut_ts = _revolut_timestamp_path()

        importers = GroupedProcess(label="Import", processes=[
            ImporterProcess(
                label="Import SMBC Prestia",
                account=SMBC_PRESTIA,
                readFromSource=lambda: readPrestiaCsv(prestia_csv, prestia_ts),
            ),
            ImporterProcess(
                label="Import Revolut",
                account=REVOLUT,
                readFromSource=lambda: readRevolutCsv(revolut_csv, revolut_ts),
            ),
        ])
        transactions = importers([])

        accounts = set(t.account for t in transactions)
        assert SMBC_PRESTIA in accounts
        assert REVOLUT in accounts

    def test_full_pipeline_no_data(self):
        """Full pipeline with no data sources produces empty results from an empty importer."""
        importer = GroupedProcess(label="Import", processes=[])
        result = importer([])
        assert result == []

    def test_complex_process_passthrough(self):
        """Complex process with no rules configured should pass through."""
        from transactflow.base import syntheticTransaction

        setUserConfig(UserConfig(
            stock=_dummy_stock_config(),
            importers=ImporterConfig(),
            processes=ProcessConfig(),
            forecast=ForecastConfig(targetYear=2025),
        ))

        from transactflow.processes.complex import process as complex_process
        complex_process._resolved = False

        t = syntheticTransaction(
            date=date(2025, 1, 1), description="Test",
            amount=MoneyAmount(JPY, -1000), category=EXPENSE, account=SMBC_PRESTIA,
        )
        result = complex_process([t])
        assert len(result) == 1
