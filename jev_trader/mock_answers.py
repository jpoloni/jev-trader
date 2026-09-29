"""Respostas SIMULADAS do Typesafe para uso offline (sem TYPESAFE_API_KEY).

Determinísticas por ticker e contínuas: tickers diferentes geram scores diferentes,
então ranking e comparador não empatam. Não representam análise real — todo resultado
gerado com elas sai com model="jev-mock".
"""
from __future__ import annotations

import hashlib
from typing import Any


def _unit(ticker: str, salt: str) -> float:
    """Valor estável em [0, 1] derivado do ticker."""
    digest = hashlib.sha256(f"{salt}:{ticker.upper().strip()}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def mock_answers_for_ticker(ticker: str) -> dict[str, Any]:
    """Mock determinístico por ticker. `u` define o viés (0 = venda, 1 = compra); `v` adiciona variação."""
    u = _unit(ticker, "vies")
    v = _unit(ticker, "ruido")

    if u > 0.66:
        choice, probs = "compra", {"compra": 0.62, "venda": 0.08, "hold": 0.30}
    elif u < 0.33:
        choice, probs = "venda", {"compra": 0.10, "venda": 0.58, "hold": 0.32}
    else:
        choice, probs = "hold", {"compra": 0.28, "venda": 0.11, "hold": 0.61}
    # <= 0.74 para não acionar o gate de divergência (confidence > 0.75)
    confidence = round(0.62 + 0.12 * abs(2 * u - 1), 3)

    return {
        "tendencia_tecnica": {"score": round(0.4 + 3.4 * u, 2)},
        "qualidade_fundamentalista": {"score": round(1.0 + 2.4 * (0.7 * u + 0.3 * v), 2)},
        "risco_volatilidade": {"score": round(2.6 - 1.6 * u, 2)},
        "sentimento_noticia": {"score": round(0.8 + 2.8 * (0.6 * u + 0.4 * v), 2)},
        "timing_momentum": {"score": round(3.8 - 3.2 * u, 2)},
        "risco_excessivo": {"noul": round(0.15 + 0.30 * (1 - u), 3)},
        "informacao_insuficiente": {"noul": round(0.10 + 0.10 * v, 3)},
        "evento_binario_iminente": {"noul": round(0.10 + 0.40 * v, 3)},
        "recomendacao": {"choice": choice, "confidence": confidence, "probabilities": probs},
    }
