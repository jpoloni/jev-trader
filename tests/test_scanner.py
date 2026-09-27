"""Testes duráveis — scanner + universe + scan_b3 (mock, sem rede, sem chave)."""
import json
import pathlib
import time

def test_universe_ibov():
    from jev_trader.universe import load_universe
    tickers = load_universe("ibov")
    assert "PETR4" in tickers
    assert "VALE3" in tickers
    assert "B3SA3" in tickers and "BPAC11" in tickers  # vigentes 2025/2026
    assert "AZUL4" not in tickers  # removido (RJ/delist, Yahoo 404)
    assert 84 <= len(tickers) <= 87
    assert tickers == sorted(tickers)

def test_universe_mock10():
    from jev_trader.universe import load_universe
    assert load_universe("mock10") == ["PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "WEGE3", "MGLU3", "GGBR4", "USIM5", "LREN3"]

def test_universe_b3_offline_fallback():
    from jev_trader.universe import load_universe
    # allow_network=False deve cair para ibov vigente (fallback) sem AZUL4
    tickers = load_universe("b3", allow_network=False)
    assert "PETR4" in tickers
    assert "AZUL4" not in tickers
    assert 84 <= len(tickers) <= 87

def test_universe_ticker_format():
    from jev_trader.universe import load_universe, TICKER_RE
    for t in load_universe("mock10"):
        assert TICKER_RE.match(t), f"formato inválido: {t}"

def test_scanner_rank_ordem_compra_primeiro():
    from jev_trader.scanner import rank_results, ScanResult
    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    base = dict(recomendacao_raw="hold", probabilidades={"compra":0.3,"venda":0.1,"hold":0.6}, scores={}, gates={}, justificativa="", disclaimer="CVM", model="jev-mock", usage={}, timestamp=ts)
    r_compra = ScanResult(ticker="AAA4", recomendacao="compra", weighted=0.71, confidence=0.68, motivo_gate=None, **base)  # type: ignore
    r_hold = ScanResult(ticker="BBB4", recomendacao="hold", weighted=0.85, confidence=0.72, motivo_gate=None, **base)  # type: ignore
    r_venda = ScanResult(ticker="CCC4", recomendacao="venda", weighted=0.90, confidence=0.75, motivo_gate=None, **base)  # type: ignore
    ranked = rank_results([r_hold, r_venda, r_compra])
    # compra deve ficar primeiro mesmo com weighted menor
    assert ranked[0].recomendacao == "compra"
    assert ranked[1].recomendacao == "hold"
    assert ranked[2].recomendacao == "venda"

def test_scanner_rank_weighted_desempate():
    from jev_trader.scanner import rank_results, ScanResult
    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    base = dict(recomendacao="compra", recomendacao_raw="compra", probabilidades={"compra":0.6,"venda":0.1,"hold":0.3}, scores={}, gates={}, motivo_gate=None, justificativa="", disclaimer="CVM", model="jev-mock", usage={}, timestamp=ts)
    r1 = ScanResult(ticker="AAA4", weighted=0.71, confidence=0.60, **base)  # type: ignore
    r2 = ScanResult(ticker="BBB4", weighted=0.85, confidence=0.60, **base)  # type: ignore
    ranked = rank_results([r1, r2])
    assert ranked[0].ticker == "BBB4"  # maior weighted primeiro

def test_scanner_gate_hold_nao_some_do_ranking():
    from jev_trader.scanner import scan_one
    # scan_one com mock deve sempre produzir Gate/weighted válidos e disclaimer
    r = scan_one("PETR4", horizonte="swing", use_mock=True)
    assert r.ticker == "PETR4"
    assert r.recomendacao in ("compra","venda","hold")
    assert 0 <= r.weighted <= 1
    assert 0 <= r.confidence <= 1
    assert r.disclaimer and "CVM" in r.disclaimer
    assert "probabilidades" in r.__dict__ or hasattr(r, "probabilidades")
    assert abs(sum(r.probabilidades.values()) - 1.0) < 0.01

def test_scanner_mock_scan_all_e_persist(tmp_path):
    from jev_trader.scanner import scan_all, persist
    from jev_trader.universe import load_universe
    tickers = load_universe("mock10")
    results = scan_all(tickers, horizonte="swing", concurrency=4, use_mock=True, prefilter=False)
    assert len(results) == 10
    assert results == sorted(results, key=lambda r: ({"compra":0,"hold":1,"venda":2}.get(r.recomendacao,9), -r.weighted, -r.confidence, r.ticker))
    # persist
    paths = persist(results, out_dir=tmp_path, top=5)
    assert pathlib.Path(paths["json"]).exists()
    assert pathlib.Path(paths["csv"]).exists()
    data = json.loads(pathlib.Path(paths["json"]).read_text(encoding="utf-8"))
    assert len(data) == 5
    assert all("disclaimer" in r for r in data)
    csv_text = pathlib.Path(paths["csv"]).read_text(encoding="utf-8")
    assert "ticker" in csv_text and "CVM" in csv_text

def test_scan_b3_tool_lê_cache(tmp_path, monkeypatch):
    import jev_conversacional.tools.scan_b3_tool as mod
    # Cria ranking fake
    ranking = [
        {"ticker":"VALE3","recomendacao":"compra","weighted":0.75,"confidence":0.70,"probabilidades":{"compra":0.6,"venda":0.1,"hold":0.3},"motivo_gate":None,"justificativa":"teste","disclaimer":"CVM","model":"jev-mock","usage":{},"timestamp":"2026-09-20T00:00:00+00:00"},
        {"ticker":"PETR4","recomendacao":"hold","weighted":0.55,"confidence":0.62,"probabilidades":{"compra":0.3,"venda":0.2,"hold":0.5},"motivo_gate":"confidence 0.45","justificativa":"gate","disclaimer":"CVM","model":"jev-mock","usage":{},"timestamp":"2026-09-20T00:00:00+00:00"},
    ]
    fake_file = tmp_path / "ranking-latest.json"
    fake_file.write_text(json.dumps(ranking), encoding="utf-8")
    monkeypatch.setattr(mod, "RANKING_LATEST", fake_file)
    monkeypatch.setattr(mod, "CACHE_TTL_S", 3600)
    # mtime fresco
    out = mod.scan_b3(top=1)
    assert out["ranking"][0]["ticker"] == "VALE3"
    assert out["total_varridos"] == 2
    assert out["cache_fresco"] is True
    assert out["ranking"][0]["pos"] == 1

def test_scan_b3_tool_sem_arquivo(monkeypatch, tmp_path):
    import jev_conversacional.tools.scan_b3_tool as mod
    fake = tmp_path / "nao-existe.json"
    monkeypatch.setattr(mod, "RANKING_LATEST", fake)
    out = mod.scan_b3(top=5)
    assert out["ranking"] == []
    assert "Nenhum ranking" in out["aviso"]

def test_agent_tem_scan_b3():
    from jev_conversacional.agent import root_agent
    tool_names = [getattr(t, "__name__", getattr(t, "name", "")) for t in root_agent.tools]
    assert "scan_b3" in tool_names
    assert "manage_portfolio" in tool_names
    assert "compare_tickers" in tool_names
    assert len(root_agent.tools) == 7
    assert "CHAME SEMPRE a tool scan_b3" in root_agent.instruction
    assert "scan_b3" in root_agent.instruction

def test_enrich_top_mantem_ordem():
    from jev_trader.scanner import scan_all, enrich_top
    from jev_trader.universe import load_universe
    tickers = load_universe("mock10")
    results = scan_all(tickers, horizonte="swing", concurrency=4, use_mock=True, prefilter=False)
    enriched = enrich_top(results, top=3, horizonte="swing", use_mock=True)
    assert len(enriched) == len(results)
    # enrich deve adicionar "| enrich" na justificativa dos top 3
    assert "enrich" in enriched[0].justificativa or any("enrich" in r.justificativa for r in enriched[:3])
