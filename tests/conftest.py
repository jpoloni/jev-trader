"""Fixtures globais: nenhum teste escreve nos arquivos reais de data/ (SQLite, carteira)."""
import pytest


@pytest.fixture(autouse=True)
def _isola_dados_locais(tmp_path, monkeypatch):
    import jev_conversacional.sqlite_storage as storage
    import jev_trader.portfolio as portfolio

    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "jev_memory.db")
    monkeypatch.setattr(portfolio, "PORTFOLIO_FILE", tmp_path / "portfolio.json")
    monkeypatch.setattr(portfolio, "TRADES_FILE", tmp_path / "trade_history.json")
