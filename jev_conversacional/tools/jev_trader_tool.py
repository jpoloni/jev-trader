"""call_jev_trader — FunctionTool ADK que encapsula Typesafe SystemOne."""
from __future__ import annotations
from typing import Any
from jev_trader.state import build_state
from jev_trader.client import call_jev_trader as _call

# assinatura exposta ao LLM via ADK FunctionTool (tipos Python viram JSON schema)
def call_jev_trader(ticker: str, horizonte_override: str | None = None, observacao_usuario: str | None = None) -> dict[str, Any]:
    """
    Chama o especialista Jev-Trader para recomendação compra/venda/hold.
    Use quando usuário pede recomendação de ação para um ticker B3.
    Args:
        ticker: Código B3, ex.: PETR4, VALE3
        horizonte_override: daytrade|swing|posicional (opcional)
        observacao_usuario: contexto extra do usuário (opcional)
    Returns:
        dict tipado {ticker, recomendacao, confidence, probabilidades, scores, gates, justificativa, disclaimer, model, usage}
    """
    # Integra market_data + ADK State será injetado pelo handler de maior nível;
    # aqui fazemos o mínimo para funcionar também em adk run sem Runner custom.
    try:
        from .market_data import get_market_data
        md = get_market_data(ticker)
    except Exception:
        md = {}

    # monta posicao_usuario a partir de horizonte_override e observation
    posicao: dict[str, Any] = {
        "tem_posicao": False,
        "perfil_risco": "moderado",
        "horizonte": horizonte_override or "swing (2-8 semanas)",
    }
    if observacao_usuario:
        posicao["observacao"] = observacao_usuario

    # noticias_7d será preenchida pelo google_search no orquestrador; aqui usa placeholder
    state = build_state(
        ticker=ticker,
        preco_atual=md.get("preco_atual"),
        variacao_dia_pct=md.get("variacao_dia_pct"),
        candles_14d=md.get("candles_14d"),
        indicadores=md.get("indicadores"),
        posicao_usuario=posicao,
        noticias_7d=["(preenchido por google_search no agente conversacional)"],
    )
    # Tenta chamada real; fallback mock se sem TYPESAFE_API_KEY
    import os
    if os.getenv("TYPESAFE_API_KEY"):
        return _call(ticker=ticker, state_override=state)
    # mock calibrado (hold com confiança moderada, gate evento_binario)
    mock_answers: dict[str, Any] = {
        "tendencia_tecnica": {"score": 3.4},
        "qualidade_fundamentalista": {"score": 3.0},
        "risco_volatilidade": {"score": 1.8},
        "sentimento_noticia": {"score": 2.8},
        "timing_momentum": {"score": 3.2},
        "risco_excessivo": {"noul": 0.31},
        "informacao_insuficiente": {"noul": 0.15},
        "evento_binario_iminente": {"noul": 0.72},
        "recomendacao": {"choice": "hold", "confidence": 0.62, "probabilities": {"compra": 0.28, "venda": 0.11, "hold": 0.61}},
    }
    return _call(ticker=ticker, state_override=state, mock_answers=mock_answers)
