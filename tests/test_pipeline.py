"""Tests for the full processing pipeline using mock data."""

import os
from datetime import date
from unittest.mock import patch

from transactflow.base import (
    EXPENSE, INCOME, SALARY, SMBC_PRESTIA, REVOLUT,
    JPY, MoneyAmount, Transaction, sortedByDate,
    GENERAL_EXPENSE_DESTINATION,
)
from transactflow.process import GroupedProcess
from transactflow.processes.importer import makeProcesses
from transactflow.processes.simple import process as simple_process
from transactflow.processes.complex import process as complex_process

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DATA_DIR = os.path.join(TESTS_DIR, "data")


class TestPipelineWithMockData:
    def _prestia_timestamp_path(self):
        return os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "last_update_time")

    def _revolut_timestamp_path(self):
        return os.path.join(TEST_DATA_DIR, "rawTransactions", "revolut", "last_update_time")

    def test_import_only(self):
        """Test that the import step loads transactions from mock CSV."""
        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")

        with patch("transactflow.importers.prestia.PRESTIA_DATA_TIMESTAMP_PATH",
                   self._prestia_timestamp_path()):
            importer = makeProcesses(prestiaCsvPath=csv_path)
            transactions = importer([])

        assert len(transactions) > 0
        assert all(t.account == SMBC_PRESTIA for t in transactions)
        # Transactions should be sorted by date
        dates = [t.date for t in transactions]
        assert dates == sorted(dates)

    def test_import_and_simple(self):
        """Test import + simple categorization.

        Note: The default simple.py only labels salary when relatedTo == EMPLOYER,
        which requires prior labelling by user-specific rules. With raw prestia
        data, income transactions without relatedTo=EMPLOYER become NOT_REALLY_INCOME.
        """
        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")

        with patch("transactflow.importers.prestia.PRESTIA_DATA_TIMESTAMP_PATH",
                   self._prestia_timestamp_path()):
            pipeline = GroupedProcess(label="Test pipeline", processes=[
                makeProcesses(prestiaCsvPath=csv_path),
                simple_process,
            ])
            transactions = pipeline([])

        assert len(transactions) > 0
        # Verify the simple process ran and categorized expense destinations
        expenses_with_dest = [
            t for t in transactions
            if t.relatedTo == GENERAL_EXPENSE_DESTINATION
        ]
        assert len(expenses_with_dest) > 0

    def test_import_multiple_sources(self):
        """Test importing from multiple sources at once."""
        prestia_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")
        revolut_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "revolut", "transactions.csv")

        with (
            patch("transactflow.importers.prestia.PRESTIA_DATA_TIMESTAMP_PATH",
                  self._prestia_timestamp_path()),
            patch("transactflow.importers.revolut.REVOLUT_DATA_TIMESTAMP_PATH",
                  self._revolut_timestamp_path()),
        ):
            importer = makeProcesses(
                prestiaCsvPath=prestia_path,
                revolutCsvPath=revolut_path,
            )
            transactions = importer([])

        accounts = set(t.account for t in transactions)
        assert SMBC_PRESTIA in accounts
        assert REVOLUT in accounts

    def test_full_pipeline_no_data(self):
        """Full pipeline with no data sources produces empty import results."""
        importer = makeProcesses()
        result = importer([])
        assert result == []

    def test_complex_process_passthrough(self):
        """Complex process with no rules configured should pass through."""
        from transactflow.base import synthesizedTransaction
        t = synthesizedTransaction(
            date=date(2025, 1, 1), description="Test",
            amount=MoneyAmount(JPY, -1000), category=EXPENSE, account=SMBC_PRESTIA,
        )
        result = complex_process([t])
        assert len(result) == 1
