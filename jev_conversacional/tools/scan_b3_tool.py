"""scan_b3 — FunctionTool ADK que lê ranking persistido e evita varredura por LLM."""
from __future__ import annotations

import json
import pathlib
import time
from typing import Any

DATA_DIR = pathlib.Path(__file__).parent.parent.parent / "data"
RANKING_LATEST = DATA_DIR / "ranking-latest.json"
CACHE_TTL_S = 15 * 60  # 15 min

AUTO_UPDATE = True

def scan_b3(
    horizonte: str = "swing",
    top: int = 10,
    force_refresh: bool = False,
    universe: str = "b3",
) -> dict[str, Any]:
    """
    Lê ranking B3 mais recente e retorna top N.

    Use para qualquer pedido de varredura/ranking ("quais as melhores ações?", "top 10").
    Não varra tickers um a um com call_jev_trader — esta tool já tem o ranking ordenado.

    Args:
        horizonte: swing|daytrade|posicional (informativo, ranking atual é swing)
        top: quantos tickers retornar (1..30)
        force_refresh: se True, força atualização síncrona do ranking
        universe: b3|ibov|curated (informativo)

    Returns:
        dict {ranking, total_varridos, gerado_em, cache_fresco, disclaimer, aviso}
    """
    import os
    top = max(1, min(30, int(top)))
    horizonte = (horizonte or "swing").strip().lower()

    needs_update = False
    if "PYTEST_CURRENT_TEST" in os.environ and not force_refresh:
        needs_update = False
    elif not AUTO_UPDATE:
        needs_update = False
    elif force_refresh or not RANKING_LATEST.exists():
        needs_update = True
    else:
        try:
            mtime = RANKING_LATEST.stat().st_mtime
            age_s = time.time() - mtime
            needs_update = age_s >= CACHE_TTL_S
        except Exception:
            needs_update = True

    aviso = None
    if needs_update:
        import subprocess
        import sys
        
        # Constrói o comando
        cmd = [
            sys.executable, "-m", "jev_trader.scanner",
            "--universe", universe,
            "--horizonte", horizonte,
            "--top", str(top),
            "--json" # Saída silenciosa
        ]
        
        if os.getenv("TYPESAFE_API_KEY"):
            cmd.append("--live")
        else:
            cmd.append("--mock")
            
        if top <= 20:
            cmd.append("--enrich")
            cmd.extend(["--enrich-top", str(top)])
            
        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=str(DATA_DIR.parent))
            aviso = "Ranking atualizado em tempo real com sucesso!"
            falhas = [l.strip() for l in (proc.stderr or "").splitlines() if l.strip()]
            if falhas:
                aviso += " Atenção — " + " ".join(falhas[:6])
        except subprocess.CalledProcessError as e:
            # Em caso de falha no update, avisar e cair no fallback de ler o cache antigo
            aviso = f"Tentativa de atualizar o scanner falhou, exibindo versão em cache. Detalhes do erro: {e.stderr.strip() or e.stdout.strip() or 'Exit code ' + str(e.returncode)}"

    if not RANKING_LATEST.exists():
        return {
            "ranking": [],
            "total_varridos": 0,
            "gerado_em": None,
            "cache_fresco": False,
            "disclaimer": "Conteúdo educacional.",
            "aviso": f"Nenhum ranking disponível ({aviso or 'arquivo não encontrado'}).",
            "horizonte_solicitado": horizonte,
        }

    try:
        data = json.loads(RANKING_LATEST.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []

        gerado_em = None
        if data and isinstance(data[0], dict) and "timestamp" in data[0]:
            gerado_em = data[0].get("timestamp")

        # Garante ordenação determinística caso arquivo esteja desordenado
        order = {"compra": 0, "hold": 1, "venda": 2}
        data_sorted = sorted(data, key=lambda r: (order.get(r.get("recomendacao", "hold"), 9), -float(r.get("weighted", 0)), -float(r.get("confidence", 0)), r.get("ticker", "")))

        top_data = data_sorted[:top]
        
        if not aviso:
            aviso = "Ranking lido do cache com sucesso."

        simulados = [r.get("ticker") for r in top_data if r.get("model") == "jev-mock"]
        if simulados:
            aviso += (
                f" ATENÇÃO: {len(simulados)} de {len(top_data)} resultados são SIMULADOS (modo mock, sem TYPESAFE_API_KEY)"
                " — não representam análise real; informe isso ao usuário."
            )

        return {
            "ranking": [
                {
                    "pos": i + 1,
                    "ticker": r.get("ticker"),
                    "recomendacao": r.get("recomendacao"),
                    "weighted": r.get("weighted"),
                    "confidence": r.get("confidence"),
                    "probabilidades": r.get("probabilidades"),
                    "motivo_gate": r.get("motivo_gate"),
                    "justificativa": r.get("justificativa"),
                    "model": r.get("model"),
                    "simulado": r.get("model") == "jev-mock",
                }
                for i, r in enumerate(top_data)
            ],
            "total_varridos": len(data),
            "gerado_em": gerado_em,
            "cache_fresco": True,
            "simulado": bool(simulados),
            "idade_min": 0 if needs_update else int((time.time() - RANKING_LATEST.stat().st_mtime) // 60),
            "disclaimer": "Conteúdo educacional. Não constitui recomendação personalizada (Res. CVM 20). Decisão final é do investidor.",
            "aviso": aviso,
            "horizonte_solicitado": horizonte,
            "horizonte_ranking": horizonte,
        }
    except Exception as e:
        return {
            "ranking": [],
            "total_varridos": 0,
            "gerado_em": None,
            "cache_fresco": False,
            "disclaimer": "Conteúdo educacional.",
            "aviso": f"Erro fatal ao ler ranking após tentativa de update: {e}",
            "horizonte_solicitado": horizonte,
        }
