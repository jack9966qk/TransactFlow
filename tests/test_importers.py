"""Tests for CSV importers using mock data from tests/data/."""

import os
import pytest
from unittest.mock import patch
from datetime import date

from transactflow.base import (
    EXPENSE, INCOME, JPY, SMBC_PRESTIA, SBI_NET_BANK, REVOLUT,
    SMBC_CREDIT_CARD, FOOD_DRINK_OUTSIDE, ENTERTAINMENT,
    EXPECTED_INTERNAL_TRANSFER, UNPAIRED_INTERNAL_TRANSFER,
    MoneyAmount, Transaction, CASH, GENERAL_EXPENSE_DESTINATION,
)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DATA_DIR = os.path.join(TESTS_DIR, "data")


class TestPrestiaImporter:
    def test_read_prestia_csv(self):
        from transactflow.importers.prestia import readPrestiaCsv

        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")
        timestamp_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "last_update_time")

        with patch("transactflow.importers.prestia.PRESTIA_DATA_TIMESTAMP_PATH", timestamp_path):
            transactions = readPrestiaCsv(csv_path)

        # 9 data rows + 1 cutoff transaction
        assert len(transactions) == 10

        incomes = [t for t in transactions if t.category == INCOME]
        expenses = [t for t in transactions if t.category == EXPENSE]
        # 3 salary transfers are income
        assert len(incomes) == 3
        # 5 expense rows + check count
        assert len(expenses) >= 4

        # Verify a specific transaction
        salary = [t for t in incomes if t.description == "Salary Transfer"]
        assert len(salary) == 3
        assert salary[0].rawAmount == MoneyAmount(JPY, 350000)
        assert salary[0].account == SMBC_PRESTIA

    def test_prestia_dates_parsed(self):
        from transactflow.importers.prestia import readPrestiaCsv

        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")
        timestamp_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "last_update_time")

        with patch("transactflow.importers.prestia.PRESTIA_DATA_TIMESTAMP_PATH", timestamp_path):
            transactions = readPrestiaCsv(csv_path)

        dates = sorted(set(t.date for t in transactions if t.description != "SMBC Prestia data source cutoff"))
        assert dates[0] == date(2025, 1, 15)
        assert dates[-1] == date(2025, 3, 25)


class TestSBIImporter:
    def test_read_sbi_csv(self):
        from transactflow.importers.sbi import readSBINetBankCSV

        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "sbi", "transactions.csv")
        timestamp_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "sbi", "last_update_time")

        with patch("transactflow.importers.sbi.SBI_DATA_TIMESTAMP_PATH", timestamp_path):
            transactions = readSBINetBankCSV(csv_path)

        # 6 data rows + 1 cutoff
        assert len(transactions) == 7

        incomes = [t for t in transactions if t.category == INCOME]
        expenses = [t for t in transactions if t.category == EXPENSE]
        assert len(incomes) == 3  # 3 salary deposits
        assert len(expenses) == 3  # 3 withdrawals

        for t in transactions:
            if t.category in (INCOME, EXPENSE):
                assert t.account == SBI_NET_BANK
                assert t.rawAmount.currency == JPY


class TestRevolutImporter:
    def test_read_revolut_csv(self):
        from transactflow.importers.revolut import readRevolutCsv

        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "revolut", "transactions.csv")
        timestamp_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "revolut", "last_update_time")

        with patch("transactflow.importers.revolut.REVOLUT_DATA_TIMESTAMP_PATH", timestamp_path):
            transactions = readRevolutCsv(csv_path)

        # 3 data rows + 1 cutoff
        assert len(transactions) == 4

        # TOPUP should be UNPAIRED_INTERNAL_TRANSFER
        topups = [t for t in transactions if t.category == UNPAIRED_INTERNAL_TRANSFER]
        assert len(topups) == 1
        assert topups[0].rawAmount.quantity == 100000

        # Card payments should be EXPENSE
        card_payments = [t for t in transactions if t.category == EXPENSE]
        assert len(card_payments) == 2


class TestManualRecordImporter:
    def test_read_manual_record_csv(self):
        from transactflow.importers.manualRecord import readManualRecordCsv

        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "manual_records.csv")
        transactions = readManualRecordCsv(csv_path)

        assert len(transactions) == 3

        food_drink = [t for t in transactions if t.category == FOOD_DRINK_OUTSIDE]
        assert len(food_drink) == 2

        entertainment = [t for t in transactions if t.category == ENTERTAINMENT]
        assert len(entertainment) == 1
        assert entertainment[0].rawAmount.quantity == -3000

        for t in transactions:
            assert t.account == CASH
            assert t.relatedTo == GENERAL_EXPENSE_DESTINATION


class TestImporterProcess:
    def test_make_processes_no_sources(self):
        """makeProcesses with no sources should create an empty import group."""
        from transactflow.processes.importer import makeProcesses

        process = makeProcesses()
        result = process([])
        assert result == []

    def test_make_processes_with_prestia(self):
        """makeProcesses with prestia path should import those transactions."""
        from transactflow.processes.importer import makeProcesses

        csv_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")
        timestamp_path = os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "last_update_time")

        with patch("transactflow.importers.prestia.PRESTIA_DATA_TIMESTAMP_PATH", timestamp_path):
            process = makeProcesses(prestiaCsvPath=csv_path)
            result = process([])

        assert len(result) > 0
        assert all(t.account == SMBC_PRESTIA for t in result)
