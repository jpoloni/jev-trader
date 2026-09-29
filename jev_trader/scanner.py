"""Scanner B3 — varredura + ranking determinístico (Typesafe jev-latest)."""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import pathlib
import time
import os
import concurrent.futures
from dataclasses import dataclass, asdict
from typing import Any
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv(pathlib.Path(__file__).parent.parent / "jev_conversacional" / ".env")

from .universe import load_universe, ALLOWLIST
from .client import call_jev_trader
from .state import build_state


# Cache dir para persistência
DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
RANKING_LATEST = DATA_DIR / "ranking-latest.json"
RANKING_CSV = DATA_DIR / "ranking-latest.csv"

@dataclass
class ScanResult:
    ticker: str
    recomendacao: str
    recomendacao_raw: str
    weighted: float
    confidence: float
    probabilidades: dict[str, float]
    scores: dict[str, float]
    gates: dict[str, float]
    motivo_gate: str | None
    justificativa: str
    disclaimer: str
    model: str
    usage: dict[str, Any]
    timestamp: str

def _mock_answers_for_ticker(ticker: str) -> dict[str, Any]:
    """Mock determinístico por ticker para testes offline — variação por hash do ticker."""
    # Hash simples para variar weighted
    h = sum(ord(c) for c in ticker) % 100
    #тики com h alto → compra, médio → hold, baixo → venda
    if h > 70:
        choice, conf, probs = "compra", 0.72, {"compra": 0.62, "venda": 0.08, "hold": 0.30}
        scores = {"tendencia_tecnica": {"score": 4.0}, "qualidade_fundamentalista": {"score": 3.8}, "risco_volatilidade": {"score": 1.2}, "sentimento_noticia": {"score": 3.5}, "timing_momentum": {"score": 1.5}}
        nouls = {"risco_excessivo": {"noul": 0.2}, "informacao_insuficiente": {"noul": 0.1}, "evento_binario_iminente": {"noul": 0.15}}
    elif h > 45:
        choice, conf, probs = "hold", 0.62, {"compra": 0.28, "venda": 0.11, "hold": 0.61}
        scores = {"tendencia_tecnica": {"score": 3.0}, "qualidade_fundamentalista": {"score": 3.0}, "risco_volatilidade": {"score": 1.8}, "sentimento_noticia": {"score": 2.8}, "timing_momentum": {"score": 2.8}}
        nouls = {"risco_excessivo": {"noul": 0.31}, "informacao_insuficiente": {"noul": 0.15}, "evento_binario_iminente": {"noul": 0.30}}
    else:
        choice, conf, probs = "venda", 0.68, {"compra": 0.10, "venda": 0.58, "hold": 0.32}
        scores = {"tendencia_tecnica": {"score": 1.2}, "qualidade_fundamentalista": {"score": 2.0}, "risco_volatilidade": {"score": 2.5}, "sentimento_noticia": {"score": 1.5}, "timing_momentum": {"score": 4.2}}
        nouls = {"risco_excessivo": {"noul": 0.35}, "informacao_insuficiente": {"noul": 0.12}, "evento_binario_iminente": {"noul": 0.20}}
    return {**scores, **nouls, "recomendacao": {"choice": choice, "confidence": conf, "probabilities": probs}}

def _prefilter_tickers(tickers: list[str], min_price: float = 2.0, concurrency: int = 8) -> list[str]:
    """Pré-filtro de liquidez em paralelo: preço > min_price, allowlist sempre passa."""
    from concurrent.futures import ThreadPoolExecutor
    from jev_conversacional.tools.market_data import get_market_data

    def _check(t: str) -> str | None:
        if t in ALLOWLIST:
            return t
        try:
            md = get_market_data(t)
        except Exception:
            return t
        preco = md.get("preco_atual")
        if preco is None:
            # Sem cotação não dá para julgar liquidez: mantém o ticker (a análise sinaliza a falta de dados)
            return t
        return t if preco >= min_price else None

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        results = list(ex.map(_check, tickers))

    return [t for t in results if t is not None]

def scan_one(ticker: str, horizonte: str = "swing", use_mock: bool = False) -> ScanResult:
    """Varre 1 ticker (bloqueante) e retorna ScanResult."""
    ticker = ticker.strip().upper()
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Monta state leve (fase 1: sem google_search)
    if use_mock:
        md = {}  # mock não precisa yfinance — evita 85 chamadas lentas
        noticias = ["(varredura sem google_search — fase 1)"]
    else:
        try:
            from jev_conversacional.tools.market_data import get_market_data
            md = get_market_data(ticker)
        except Exception:
            md = {}
        noticias = md.get("noticias_recentes") or ["(varredura sem google_search — fase 1)"]

    state = build_state(
        ticker=ticker,
        nome=md.get("nome"),
        setor=md.get("setor"),
        preco_atual=md.get("preco_atual"),
        variacao_dia_pct=md.get("variacao_dia_pct"),
        candles_14d=md.get("candles_14d"),
        indicadores=md.get("indicadores"),
        fundamentos=md.get("fundamentos"),
        noticias_7d=noticias,
        posicao_usuario={"tem_posicao": False, "perfil_risco": "moderado", "horizonte": horizonte},
    )

    if use_mock:
        mock = _mock_answers_for_ticker(ticker)
        out = call_jev_trader(ticker=ticker, state_override=state, mock_answers=mock)
    else:
        # Modo live: falhas propagam — nunca substituir por resposta simulada
        out = call_jev_trader(ticker=ticker, state_override=state)

    return ScanResult(
        ticker=out["ticker"],
        recomendacao=out["recomendacao"],
        recomendacao_raw=out["recomendacao_raw"],
        weighted=out["weighted"],
        confidence=out["confidence"],
        probabilidades=out["probabilidades"],
        scores=out["scores"],
        gates=out["gates"],
        motivo_gate=out["motivo_gate"],
        justificativa=out["justificativa"],
        disclaimer=out["disclaimer"],
        model=out["model"],
        usage=out["usage"],
        timestamp=ts,
    )

def rank_results(results: list[ScanResult]) -> list[ScanResult]:
    """Ordenação determinística: compra primeiro, depois weighted desc, confidence desc, ticker asc."""
    order = {"compra": 0, "hold": 1, "venda": 2}
    return sorted(results, key=lambda r: (order.get(r.recomendacao, 9), -r.weighted, -r.confidence, r.ticker))

def scan_all(
    tickers: list[str],
    horizonte: str = "swing",
    concurrency: int = 8,
    use_mock: bool = False,
    prefilter: bool = True,
    show_progress: bool = True,
    errors: list[str] | None = None,
) -> list[ScanResult]:
    """Varre todos os tickers com ThreadPoolExecutor (limitado por concurrency).

    Tickers que falham ficam fora do ranking; se `errors` for passado, recebe "TICKER: motivo".
    """
    if prefilter and not use_mock:
        tickers = _prefilter_tickers(tickers, concurrency=concurrency)
    elif prefilter and use_mock:
        # Em mock, não filtra (mantém determinismo)
        pass

    results: list[ScanResult] = []
    if errors is None:
        errors = []

    pbar = None
    if show_progress:
        from .cli_ui import ScanProgressBar
        pbar = ScanProgressBar(total=len(tickers), description=f"Varrendo ({horizonte})")

    def _task(t: str) -> ScanResult | None:
        for attempt in range(3):
            try:
                return scan_one(t, horizonte=horizonte, use_mock=use_mock)
            except Exception as e:
                msg = str(e)
                if "429" in msg or "rate" in msg.lower():
                    time.sleep(1 * (2 ** attempt) + (attempt * 0.3))
                    continue
                # Outros erros: ticker fica fora do ranking (sem fallback para mock)
                errors.append(f"{t}: {e}")
                return None
        errors.append(f"{t}: retry exhausted")
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        future_to_ticker = {executor.submit(_task, t): t for t in tickers}
        for fut in concurrent.futures.as_completed(future_to_ticker):
            t = future_to_ticker[fut]
            res = fut.result()
            if res is not None:
                results.append(res)
            if pbar:
                pbar.update(1, current_ticker=t)

    if pbar:
        pbar.finish()

    return rank_results(results)


def persist(results: list[ScanResult], out_dir: str | pathlib.Path | None = None, top: int | None = None) -> dict[str, str]:
    """Persiste ranking em JSON (latest + dated) e CSV. Retorna paths."""
    base = pathlib.Path(out_dir) if out_dir else DATA_DIR
    base.mkdir(parents=True, exist_ok=True)

    to_save = results[:top] if top else results
    data = [asdict(r) for r in to_save]
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")

    latest_json = base / "ranking-latest.json"
    dated_json = base / f"ranking-{timestamp}.json"
    csv_path = base / "ranking-latest.csv"

    latest_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker", "recomendacao", "recomendacao_raw", "weighted", "confidence", "motivo_gate", "model", "timestamp", "disclaimer"])
        writer.writeheader()
        for r in to_save:
            writer.writerow({
                "ticker": r.ticker,
                "recomendacao": r.recomendacao,
                "recomendacao_raw": r.recomendacao_raw,
                "weighted": r.weighted,
                "confidence": r.confidence,
                "motivo_gate": r.motivo_gate or "",
                "model": r.model,
                "timestamp": r.timestamp,
                "disclaimer": r.disclaimer,
            })

    # Rotação: mantém 30 dias
    for p in sorted(base.glob("ranking-*.json"))[:-30]:
        try:
            if p.name != "ranking-latest.json":
                p.unlink()
        except Exception:
            pass

    out_paths = {"json": str(latest_json), "dated": str(dated_json), "csv": str(csv_path)}

    # Gera planilhas Excel e CSV legível formatado automaticamente
    try:
        from scripts.export_spreadsheet import generate_spreadsheets
        generate_spreadsheets(latest_json, quiet=True)
        excel_path = base / "ranking-latest.xlsx"
        legivel_path = base / "ranking-latest-legivel.csv"
        if excel_path.exists():
            out_paths["excel"] = str(excel_path)
        if legivel_path.exists():
            out_paths["csv_legivel"] = str(legivel_path)
    except Exception:
        pass

    return out_paths

def enrich_top(
    results: list[ScanResult],
    top: int = 20,
    horizonte: str = "swing",
    use_mock: bool = False,
    show_progress: bool = True,
    errors: list[str] | None = None,
) -> list[ScanResult]:
    """Fase 2: re-enriquece Top N com google_search (se disponível) + re-call Typesafe."""
    if not results or top <= 0:
        return results
    top_n = results[:top]
    rest = results[top:]

    pbar = None
    if show_progress:
        from .cli_ui import ScanProgressBar
        pbar = ScanProgressBar(total=len(top_n), description="Enriquecendo Top N")

    enriched: list[ScanResult] = []
    for r in top_n:
        try:
            if use_mock:
                md = {}
                noticias = [f"Notícia enriquecida para {r.ticker} (fase 2)"]
            else:
                from jev_conversacional.tools.market_data import get_market_data
                md = get_market_data(r.ticker)
                noticias = md.get("noticias_recentes")
                if not noticias:
                    try:
                        from .news_feed import get_news_feed
                        noticias = get_news_feed(r.ticker, limit=4)
                    except Exception:
                        noticias = [f"Notícia enriquecida para {r.ticker} (fase 2)"]

            state = build_state(
                ticker=r.ticker,
                nome=md.get("nome"),
                setor=md.get("setor"),
                preco_atual=md.get("preco_atual"),
                variacao_dia_pct=md.get("variacao_dia_pct"),
                candles_14d=md.get("candles_14d"),
                indicadores=md.get("indicadores"),
                fundamentos=md.get("fundamentos"),
                noticias_7d=noticias,
                posicao_usuario={"tem_posicao": False, "perfil_risco": "moderado", "horizonte": horizonte},
            )
            if use_mock:
                mock = _mock_answers_for_ticker(r.ticker)
                out = call_jev_trader(ticker=r.ticker, state_override=state, mock_answers=mock)
            else:
                # Modo live: falhas propagam — mantém o resultado da fase 1, nunca um mock
                out = call_jev_trader(ticker=r.ticker, state_override=state)

            new_r = ScanResult(
                ticker=out["ticker"],
                recomendacao=out["recomendacao"],
                recomendacao_raw=out["recomendacao_raw"],
                weighted=out["weighted"],
                confidence=out["confidence"],
                probabilidades=out["probabilidades"],
                scores=out["scores"],
                gates=out["gates"],
                motivo_gate=out["motivo_gate"],
                justificativa=out["justificativa"] + " | enrich fase 2",
                disclaimer=out["disclaimer"],
                model=out["model"],
                usage=out["usage"],
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            enriched.append(new_r)
        except Exception as e:
            if errors is not None:
                errors.append(f"{r.ticker} (enrich): {e}")
            enriched.append(r)
        finally:
            if pbar:
                pbar.update(1, current_ticker=r.ticker)

    if pbar:
        pbar.finish()

    # Re-rank após enrich (pode mudar ordem)
    return rank_results(enriched + rest)

def main():
    parser = argparse.ArgumentParser(description="Jev Scanner — Varredura B3 e ranking determinístico")
    parser.add_argument("--universe", default="b3", help="b3|ibov|curated|mock10|file")
    parser.add_argument("--horizonte", default="swing", help="swing|daytrade|posicional")
    parser.add_argument("--top", type=int, default=20, help="quantos ativos exibir no ranking final")
    parser.add_argument("--concurrency", type=int, default=8, help="número de threads paralelas")
    parser.add_argument("--mock", action="store_true", help="usa mock_answers (offline, sem chave)")
    parser.add_argument("--live", action="store_true", help="força modo live (requer TYPESAFE_API_KEY)")
    parser.add_argument("--enrich", action="store_true", help="fase 2: re-enriquece Top N com dados de mercado")
    parser.add_argument("--enrich-top", type=int, default=20, help="quantos ativos enriquecer na fase 2")
    parser.add_argument("--out", default=None, help="diretório de saída (default: data/)")
    parser.add_argument("--no-prefilter", action="store_true", help="desativa pré-filtro de liquidez")
    parser.add_argument("--json", action="store_true", help="emite saída como JSON puro (para automações/pipes)")
    parser.add_argument("--no-color", action="store_true", help="desativa cores ANSI")
    parser.add_argument("--no-progress", action="store_true", help="desativa barra de progresso interativa")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    start_time = time.time()

    if args.no_color:
        from .cli_ui import set_color_enabled
        set_color_enabled(False)

    if args.live:
        use_mock = False
    elif args.mock:
        use_mock = True
    else:
        use_mock = not bool(os.getenv("TYPESAFE_API_KEY"))

    mode_desc = "MOCK (offline)" if use_mock else "LIVE (Typesafe API)"

    tickers = load_universe(source=args.universe, cache_path=DATA_DIR / "universe.json")

    if not args.json:
        from .cli_ui import print_banner
        print_banner(
            "JEV SCANNER B3 — Varredura & Ranking de Ações",
            f"Universo: {args.universe.upper()} ({len(tickers)} ativos) │ Modo: {mode_desc} │ Horizonte: {args.horizonte} │ Concorrência: {args.concurrency}",
        )

    errors: list[str] = []
    results = scan_all(
        tickers,
        horizonte=args.horizonte,
        concurrency=args.concurrency,
        use_mock=use_mock,
        prefilter=not args.no_prefilter,
        show_progress=not (args.json or args.no_progress),
        errors=errors,
    )

    if args.enrich:
        results = enrich_top(
            results,
            top=args.enrich_top,
            horizonte=args.horizonte,
            use_mock=use_mock,
            show_progress=not (args.json or args.no_progress),
            errors=errors,
        )

    if errors:
        import sys
        print(f"⚠️  {len(errors)} falha(s) na varredura (tickers fora do ranking ou sem enrich):", file=sys.stderr)
        for err in errors[:20]:
            print(f"   - {err}", file=sys.stderr)
        if len(errors) > 20:
            print(f"   ... e mais {len(errors) - 20}", file=sys.stderr)

    if not results:
        import sys
        print("❌ Nenhum ativo analisado com sucesso — ranking anterior mantido.", file=sys.stderr)
        sys.exit(1)

    paths = persist(results, out_dir=args.out, top=args.top)
    elapsed = time.time() - start_time

    if args.json:
        import json
        print(json.dumps([asdict(r) for r in results[:args.top]], ensure_ascii=False, indent=2))
    else:
        from .cli_ui import render_ranking_table, render_scan_summary
        print(render_ranking_table(results, top=args.top, horizonte=args.horizonte))
        print(render_scan_summary(results, paths, universe_name=args.universe.upper(), horizonte=args.horizonte, duration_s=elapsed))

if __name__ == "__main__":
    main()

