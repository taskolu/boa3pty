import pytest
import json
from src.core.config import ConfigManager


@pytest.fixture
def config_file(tmp_path):
    cfg = {
        "archive_path": str(tmp_path / "archive"),
        "counterparties": {
            "BankA": {
                "csv_bank_code": "BANKA_GPG",
                "wallstreet_counterparty_name": "Bank A International",
                "csv_column_mapping": {
                    "payment_id": "Payment ID",
                    "confirmation_number": "Payment Reference",
                    "buy_currency": "Currency",
                    "buy_amount": "Amount",
                    "value_date": "Value Date",
                    "status_code": "Status Information/Error"
                },
                "date_format": "%Y-%m-%d",
                "dt06_code": "DT06",
                "lookback_days": 5,
                "auto_resolve_dt06": False,
                "rules": ["dt06_date_change"],
                "wallstreet_column_mapping": {}
            }
        }
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    return str(path)


def test_load_config(config_file):
    cm = ConfigManager(config_file)
    assert cm.archive_path is not None
    assert "BankA" in cm.counterparty_names


def test_get_counterparty(config_file):
    cm = ConfigManager(config_file)
    cp = cm.get_counterparty("BankA")
    assert cp["csv_bank_code"] == "BANKA_GPG"
    assert cp["lookback_days"] == 5


def test_find_counterparty_by_bank_code(config_file):
    cm = ConfigManager(config_file)
    name = cm.find_by_bank_code("BANKA_GPG")
    assert name == "BankA"


def test_find_counterparty_by_ws_name(config_file):
    cm = ConfigManager(config_file)
    name = cm.find_by_ws_name("Bank A International")
    assert name == "BankA"


def test_unknown_bank_code_returns_none(config_file):
    cm = ConfigManager(config_file)
    assert cm.find_by_bank_code("UNKNOWN") is None


def test_add_counterparty(config_file):
    cm = ConfigManager(config_file)
    cm.add_counterparty("BankB", {
        "csv_bank_code": "BANKB_GPG",
        "wallstreet_counterparty_name": "Bank B Corp",
        "csv_column_mapping": {},
        "date_format": "%d/%m/%Y",
        "dt06_code": "DT06",
        "lookback_days": 3,
        "auto_resolve_dt06": True,
        "rules": [],
        "wallstreet_column_mapping": {}
    })
    cm.save()
    cm2 = ConfigManager(config_file)
    assert "BankB" in cm2.counterparty_names
