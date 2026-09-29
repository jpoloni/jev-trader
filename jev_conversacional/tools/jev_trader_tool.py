"""call_jev_trader — FunctionTool ADK que encapsula Typesafe SystemOne."""
from __future__ import annotations
from typing import Any
from jev_trader.state import build_state
from jev_trader.client import call_jev_trader as _call

# assinatura exposta ao LLM via ADK FunctionTool (tipos Python viram JSON schema)
def call_jev_trader(ticker: str, horizonte_override: str | None = None, observacao_usuario: str | None = None, noticias_relevantes: list[str] | None = None) -> dict[str, Any]:
    """
    Chama o especialista Jev-Trader para recomendação compra/venda/hold.
    Use quando usuário pede recomendação de ação para um ticker B3.
    Args:
        ticker: Código B3, ex.: PETR4, VALE3
        horizonte_override: daytrade|swing|posicional (opcional)
        observacao_usuario: contexto extra do usuário (opcional)
        noticias_relevantes: lista de manchetes ou resumos de notícias encontrados pelo google_search (opcional)
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

    # monta posicao_usuario a partir de horizonte_override, observacao e carteira pessoal
    posicao: dict[str, Any] = {
        "tem_posicao": False,
        "perfil_risco": "moderado",
        "horizonte": horizonte_override or "swing (2-8 semanas)",
    }
    try:
        from jev_trader.portfolio import get_position
        pos_detalhe = get_position(ticker)
        if pos_detalhe:
            posicao["tem_posicao"] = True
            posicao["quantidade"] = pos_detalhe["quantidade"]
            posicao["preco_medio"] = pos_detalhe["preco_medio"]
            posicao["pct_carteira"] = pos_detalhe["pct_carteira"]
            posicao["pl_pct"] = pos_detalhe["pl_pct"]
    except Exception:
        pass

    if observacao_usuario:
        posicao["observacao"] = observacao_usuario

    # noticias_relevantes fornecido pelo orquestrador via google_search ou fallback news feed
    if not noticias_relevantes:
        noticias_relevantes = md.get("noticias_recentes")
        if not noticias_relevantes:
            try:
                from jev_trader.news_feed import get_news_feed
                noticias_relevantes = get_news_feed(ticker, limit=4)
            except Exception:
                noticias_relevantes = ["(Sem notícias injetadas pelo orquestrador)"]

    state = build_state(
        ticker=ticker,
        nome=md.get("nome"),
        setor=md.get("setor"),
        preco_atual=md.get("preco_atual"),
        variacao_dia_pct=md.get("variacao_dia_pct"),
        candles_14d=md.get("candles_14d"),
        indicadores=md.get("indicadores"),
        fundamentos=md.get("fundamentos"),
        posicao_usuario=posicao,
        noticias_7d=noticias_relevantes,
    )
    # Tenta chamada real; fallback mock se sem TYPESAFE_API_KEY
    import os
    if os.getenv("TYPESAFE_API_KEY"):
        res = _call(ticker=ticker, state_override=state)
    else:
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
        res = _call(ticker=ticker, state_override=state, mock_answers=mock_answers)

    # Deixa explícito ao orquestrador se a análise teve cotação real
    res["dados_mercado"] = {
        "disponivel": md.get("disponivel", False),
        "simulado": md.get("simulado", False),
        "fonte": md.get("fonte", "indisponivel"),
    }

    # Persiste recomendação no histórico SQLite para tracking de acurácia
    try:
        from ..sqlite_storage import log_recommendation
        log_recommendation(
            ticker=ticker,
            recomendacao=res.get("recomendacao", "hold"),
            score_ponderado=float(res.get("weighted", 0.0)),
            confianca=float(res.get("confidence", 0.0)),
            preco=md.get("preco_atual"),
        )
    except Exception:
        pass

    return res
