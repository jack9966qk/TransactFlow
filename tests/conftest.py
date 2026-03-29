import os
import sys
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DATA_DIR = os.path.join(TESTS_DIR, "data")


@pytest.fixture
def test_data_dir():
    """Return the path to the tests/data/ directory."""
    return TEST_DATA_DIR


@pytest.fixture
def mock_prestia_csv():
    return os.path.join(TEST_DATA_DIR, "rawTransactions", "prestia", "combined.csv")


@pytest.fixture
def mock_sbi_csv():
    return os.path.join(TEST_DATA_DIR, "rawTransactions", "sbi", "transactions.csv")


@pytest.fixture
def mock_revolut_csv():
    return os.path.join(TEST_DATA_DIR, "rawTransactions", "revolut", "transactions.csv")


@pytest.fixture
def mock_smbc_card_dir():
    return os.path.join(TEST_DATA_DIR, "rawTransactions", "smbc-card", "months")


@pytest.fixture
def mock_manual_record_csv():
    return os.path.join(TEST_DATA_DIR, "rawTransactions", "manual_records.csv")
