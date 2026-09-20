"""State canônico Jev-Trader — objeto 6 chaves, texto apenas."""
from __future__ import annotations
from typing import Any
import json

REQUIRED_TOP_KEYS = ["ativo", "mercado", "fundamentos", "contexto", "posicao_usuario", "restricoes"]

def build_state(
    *,
    ticker: str,
    nome: str | None = None,
    setor: str | None = None,
    preco_atual: float | None = None,
    variacao_dia_pct: float | None = None,
    candles_14d: list[dict[str, Any]] | None = None,
    indicadores: dict[str, Any] | None = None,
    tendencia_descritiva: str | None = None,
    fundamentos: dict[str, Any] | None = None,
    noticias_7d: list[str] | None = None,
    eventos_proximos: list[str] | None = None,
    sentimento_mercado: str | None = None,
    posicao_usuario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "ativo": {
            "ticker": ticker.upper().strip(),
            "nome": nome or ticker.upper(),
            "setor": setor or "Não informado",
            "bolsa": "B3",
        },
        "mercado": {
            "preco_atual": preco_atual,
            "variacao_dia_pct": variacao_dia_pct,
            "candles_14d": (candles_14d or [])[:20],
            "indicadores": indicadores or {},
            "tendencia_descritiva": tendencia_descritiva or "Não informado",
        },
        "fundamentos": fundamentos or {"observacao": "Não informado"},
        "contexto": {
            "noticias_7d": (noticias_7d or [])[:8],
            "eventos_proximos": (eventos_proximos or [])[:5],
            "sentimento_mercado": sentimento_mercado or "Não informado",
        },
        "posicao_usuario": posicao_usuario or {"tem_posicao": False, "perfil_risco": "moderado", "horizonte": "swing (2-8 semanas)"},
        "restricoes": {
            "disclaimer": "Análise educacional, não é recomendação de investimento personalizada (Res. CVM 20). Decisão final é do investidor."
        },
    }
    return state


def validate_state(state: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    for k in REQUIRED_TOP_KEYS:
        if k not in state:
            errs.append(f"missing top key: {k}")
    # backtick anchoring hint: state deve ser objeto, não blob
    if not isinstance(state.get("ativo", {}).get("ticker"), str):
        errs.append("ativo.ticker deve ser string")
    return errs


def state_to_json(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, indent=2)
