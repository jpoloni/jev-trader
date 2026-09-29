"""Garantias de confiabilidade: nenhum preço ou recomendação simulada passa como real."""
import json
import sys
import types

import pytest


def _yfinance_quebrado(monkeypatch):
    fake = types.ModuleType("yfinance")

    def _ticker(_symbol):
        raise ConnectionError("sem rede")

    fake.Ticker = _ticker
    monkeypatch.setitem(sys.modules, "yfinance", fake)


@pytest.fixture
def md_mod(monkeypatch):
    import jev_conversacional.tools.market_data as mod
    monkeypatch.setattr(mod, "_CACHE", {})
    monkeypatch.delenv("JEV_MARKET_MOCK", raising=False)
    return mod


def test_market_data_falha_nao_inventa_preco(md_mod, monkeypatch):
    _yfinance_quebrado(monkeypatch)
    data = md_mod.get_market_data("ZZZZ3")
    assert data["preco_atual"] is None
    assert data["disponivel"] is False
    assert data["simulado"] is False
    assert data["fonte"] == "indisponivel"
    # falha não é cacheada
    assert "ZZZZ3" not in md_mod._CACHE


def test_market_data_mock_so_quando_pedido(md_mod, monkeypatch):
    monkeypatch.setenv("JEV_MARKET_MOCK", "1")
    data = md_mod.get_market_data("PETR4")
    assert data["simulado"] is True
    assert data["preco_atual"] is not None
    assert "simulado" in data["fonte"]


def test_carteira_sem_cotacao_nao_calcula_pl(tmp_path, monkeypatch, md_mod):
    import jev_trader.portfolio as p_mod
    monkeypatch.setattr(p_mod, "PORTFOLIO_FILE", tmp_path / "portfolio.json")
    monkeypatch.setattr(p_mod, "TRADES_FILE", tmp_path / "trade_history.json")
    _yfinance_quebrado(monkeypatch)

    p_mod.buy_asset("PETR4", 100, 42.0)
    summary = p_mod.get_portfolio_summary()
    pos = summary["posicoes"][0]
    assert pos["cotacao_disponivel"] is False
    assert pos["preco_atual"] is None
    assert pos["pl_reais"] is None and pos["pl_pct"] is None
    assert pos["valor_atual"] == 4200.0  # valorizado pelo preço médio, não por preço fictício
    assert summary["cotacoes_indisponiveis"] == ["PETR4"]
    assert "indisponível" in summary["aviso"]

    detalhe = p_mod.get_position("PETR4")
    assert detalhe["cotacao_disponivel"] is False and detalhe["pl_pct"] is None


def test_carteira_com_cotacao_simulada_e_sinalizada(tmp_path, monkeypatch, md_mod):
    import jev_trader.portfolio as p_mod
    monkeypatch.setattr(p_mod, "PORTFOLIO_FILE", tmp_path / "portfolio.json")
    monkeypatch.setattr(p_mod, "TRADES_FILE", tmp_path / "trade_history.json")
    monkeypatch.setenv("JEV_MARKET_MOCK", "1")

    p_mod.buy_asset("VALE3", 10, 60.0)
    summary = p_mod.get_portfolio_summary()
    assert summary["cotacoes_simuladas"] == ["VALE3"]
    assert "SIMULADA" in summary["aviso"]


def test_scanner_live_falha_nao_vira_mock(monkeypatch, md_mod):
    import jev_trader.scanner as sc
    _yfinance_quebrado(monkeypatch)

    def _falha(**kwargs):
        if kwargs.get("mock_answers") is not None:
            pytest.fail("modo live não pode cair para mock_answers")
        raise RuntimeError("Typesafe fora do ar")

    monkeypatch.setattr(sc, "call_jev_trader", _falha)
    errors: list[str] = []
    results = sc.scan_all(["PETR4", "VALE3"], use_mock=False, prefilter=False, show_progress=False, errors=errors)
    assert results == []
    assert len(errors) == 2 and all("Typesafe fora do ar" in e for e in errors)


def test_scanner_enrich_live_falha_mantem_fase1(monkeypatch, md_mod):
    import jev_trader.scanner as sc
    _yfinance_quebrado(monkeypatch)
    fase1 = sc.scan_all(["PETR4", "VALE3"], use_mock=True, prefilter=False, show_progress=False)

    def _falha(**kwargs):
        if kwargs.get("mock_answers") is not None:
            pytest.fail("modo live não pode cair para mock_answers")
        raise RuntimeError("Typesafe fora do ar")

    monkeypatch.setattr(sc, "call_jev_trader", _falha)
    errors: list[str] = []
    out = sc.enrich_top(fase1, top=2, use_mock=False, show_progress=False, errors=errors)
    assert [r.ticker for r in out] == [r.ticker for r in fase1]
    assert len(errors) == 2


def test_scan_b3_sinaliza_ranking_simulado(tmp_path, monkeypatch):
    import jev_conversacional.tools.scan_b3_tool as mod
    fake = tmp_path / "ranking-latest.json"
    fake.write_text(json.dumps([
        {"ticker": "VALE3", "recomendacao": "compra", "weighted": 0.7, "confidence": 0.7, "model": "jev-mock", "timestamp": "2026-09-20T00:00:00+00:00"},
    ]), encoding="utf-8")
    monkeypatch.setattr(mod, "RANKING_LATEST", fake)
    monkeypatch.setattr(mod, "CACHE_TTL_S", 3600)
    out = mod.scan_b3(top=5)
    assert out["simulado"] is True
    assert out["ranking"][0]["simulado"] is True
    assert "SIMULADOS" in out["aviso"]


def test_mock_varia_por_ticker_e_nao_polui_historico(monkeypatch, md_mod):
    from jev_conversacional.tools.compare_tool import compare_tickers
    import jev_conversacional.sqlite_storage as storage
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("JEV_MARKET_MOCK", "1")

    res = compare_tickers(["PETR4", "VALE3", "ITUB4"])
    scores = [c["score_ponderado"] for c in res["comparativo"]]
    assert len(set(scores)) == 3  # sem empate artificial
    assert res["simulado"] is True and "SIMULADAS" in res["aviso"]
    assert all(c["simulado"] for c in res["comparativo"])
    # recomendações simuladas não entram no histórico de acurácia
    assert storage.get_past_recommendations() == []


def test_mock_answers_deterministico():
    from jev_trader.mock_answers import mock_answers_for_ticker
    assert mock_answers_for_ticker("PETR4") == mock_answers_for_ticker("petr4")
    assert mock_answers_for_ticker("PETR4") != mock_answers_for_ticker("VALE3")
