from unittest.mock import MagicMock

import pytest

from src.core.connection import IBConnectionManager
from src.core.exceptions import ConnectionError


def test_connect_failure(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.connect.side_effect = Exception("boom")
    monkeypatch.setattr("src.core.connection.IB", lambda: fake_ib)

    config = MagicMock(host="h", port=1, client_id=2, account_id="A")
    manager = IBConnectionManager(config)

    with pytest.raises(ConnectionError):
        manager.connect()

    assert manager.ib is None
    assert not manager._is_connected


def test_connection_context_manager(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True
    fake_ib.connect.return_value = None
    fake_ib.disconnect.return_value = None
    monkeypatch.setattr("src.core.connection.IB", lambda: fake_ib)

    config = MagicMock(host="h", port=1, client_id=2, account_id="A")
    manager = IBConnectionManager(config)

    with manager.connection() as ib:
        assert ib is fake_ib

    fake_ib.disconnect.assert_called_once()

def test_ensure_connected(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.connect.return_value = None
    fake_ib.isConnected.return_value = True
    monkeypatch.setattr("src.core.connection.IB", lambda: fake_ib)

    config = MagicMock(host="h", port=1, client_id=2, account_id="A")
    manager = IBConnectionManager(config)
    manager.connect()

    manager.ensure_connected()
    fake_ib.connect.assert_called_once()

def test_connect_success_and_disconnect(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True
    fake_ib.connect.return_value = None
    fake_ib.disconnect.return_value = None
    monkeypatch.setattr("src.core.connection.IB", lambda: fake_ib)

    config = MagicMock(host="h", port=1, client_id=2, account_id="A")
    manager = IBConnectionManager(config)

    ib = manager.connect()
    assert ib is fake_ib
    assert manager._is_connected

    manager.disconnect()
    fake_ib.disconnect.assert_called_once()


def test_connect_managed_accounts_empty(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True
    fake_ib.connect.return_value = None
    fake_ib.managedAccounts.return_value = []
    fake_ib.disconnect.return_value = None
    monkeypatch.setattr("src.core.connection.IB", lambda: fake_ib)

    config = MagicMock(host="h", port=1, client_id=2, account_id="A")
    manager = IBConnectionManager(config)

    with pytest.raises(ConnectionError):
        manager.connect()

    assert fake_ib.managedAccounts.call_count >= 1
