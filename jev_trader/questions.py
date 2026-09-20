"""Questions Jev-Trader — 9 perguntas (5 Score + 3 Noul + 1 Choice) em 1 chamada."""
from __future__ import annotations

# Imports condicionais: funciona com typesafe-sdk instalado e em testes mockados
try:
    from typesafe_sdk import Choice, Noul, Score  # type: ignore
    HAS_TYPESAFE = True
except Exception:  # pragma: no cover
    HAS_TYPESAFE = False
    Choice = Noul = Score = object  # placeholder para type check em testes


def build_questions():
    """Retorna dict questions pronto para TypeSafeClient.system_one(state, questions)."""
    if not HAS_TYPESAFE:
        # fallback dict cru para testes sem SDK
        return _build_questions_raw()
    return {
        "tendencia_tecnica": Score(
            instructions="Given `mercado.candles_14d`, `mercado.indicadores` and `mercado.tendencia_descritiva`, how strong is the technical trend?",
            criteria=[
                "Strong downtrend — clear lower highs/lows, momentum negative",
                "Weak downtrend — slight negative bias",
                "Neutral / sideways — no clear direction",
                "Weak uptrend — slight positive bias",
                "Strong uptrend — clear higher highs/lows, momentum positive",
            ],
        ),
        "qualidade_fundamentalista": Score(
            instructions="Given `fundamentos` and `ativo.setor`, how strong are fundamentals for a 2-8 week horizon?",
            criteria=[
                "Very weak — expensive or deteriorating, high leverage",
                "Weak — below sector average",
                "Average — fair valuation, stable",
                "Strong — attractive valuation and solid profitability",
                "Very strong — cheap, highly profitable, low leverage",
            ],
        ),
        "risco_volatilidade": Score(
            instructions="Given `mercado.indicadores.volatilidade_20d_pct`, `mercado.volume_vs_media_20d`, `contexto.eventos_proximos` and `posicao_usuario.pct_carteira`, what is downside risk/volatility?",
            criteria=[
                "Low risk — low vol, no near catalyst, small position",
                "Moderate risk",
                "High risk — elevated vol or large position or near event",
                "Extreme risk — very high vol and binary event imminent",
            ],
        ),
        "sentimento_noticia": Score(
            instructions="Given `contexto.noticias_7d` and `contexto.sentimento_mercado`, what is news/sentiment tone for `ativo.ticker`?",
            criteria=[
                "Very negative — multiple adverse catalysts",
                "Slightly negative",
                "Neutral / mixed",
                "Slightly positive",
                "Very positive — clear tailwinds",
            ],
        ),
        "timing_momentum": Score(
            instructions="Given `mercado.indicadores.rsi_14`, `mercado.variacao_dia_pct` and `mercado.indicadores.mm_20_vs_50`, is timing stretched?",
            criteria=[
                "Deeply oversold — contrarian buy timing",
                "Oversold — favorable for entry",
                "Neutral — no timing edge",
                "Overbought — unfavorable for entry",
                "Deeply overbought — high pullback risk",
            ],
        ),
        "risco_excessivo": Noul(
            instructions="Does `mercado` + `contexto.eventos_proximos` + `posicao_usuario` indicate that a new buy would risk a disproportionate loss vs expected gain?"
        ),
        "informacao_insuficiente": Noul(
            instructions="Is `fundamentos` or `contexto.noticias_7d` missing or contradictory to the point that a buy/sell decision would be a guess?"
        ),
        "evento_binario_iminente": Noul(
            instructions="Is there a binary event in `contexto.eventos_proximos` within ~10 days that makes direction highly uncertain (earnings, Copom, etc.)?"
        ),
        "recomendacao": Choice(
            instructions="Given all fields in state, which action best fits a `posicao_usuario.horizonte` and `posicao_usuario.perfil_risco` investor?",
            criteria={
                "compra": "Open or increase long position now — risk/reward favors entry",
                "venda": "Close or reduce position now — risk/reward favors exit",
                "hold": "Do nothing — wait for better price or more information",
            },
        ),
    }


def _build_questions_raw() -> dict:
    """Fallback sem SDK — usado em testes que validam estrutura."""
    return {
        "tendencia_tecnica": {"type": "score", "instructions": "Given `mercado.candles_14d`, `mercado.indicadores` and `mercado.tendencia_descritiva`, how strong is the technical trend?", "criteria": ["Strong downtrend", "Weak downtrend", "Neutral", "Weak uptrend", "Strong uptrend"]},
        "qualidade_fundamentalista": {"type": "score", "instructions": "Given `fundamentos` and `ativo.setor`, how strong are fundamentals?", "criteria": ["Very weak", "Weak", "Average", "Strong", "Very strong"]},
        "risco_volatilidade": {"type": "score", "instructions": "Given `mercado.indicadores.volatilidade_20d_pct`, what is downside risk?", "criteria": ["Low", "Moderate", "High", "Extreme"]},
        "sentimento_noticia": {"type": "score", "instructions": "Given `contexto.noticias_7d` and `contexto.sentimento_mercado`, what is tone?", "criteria": ["Very negative", "Slightly negative", "Neutral", "Slightly positive", "Very positive"]},
        "timing_momentum": {"type": "score", "instructions": "Given `mercado.indicadores.rsi_14`, is timing stretched?", "criteria": ["Deeply oversold", "Oversold", "Neutral", "Overbought", "Deeply overbought"]},
        "risco_excessivo": {"type": "noul", "instructions": "Does `mercado` indicate disproportionate loss risk?"},
        "informacao_insuficiente": {"type": "noul", "instructions": "Is `fundamentos` missing/contradictory?"},
        "evento_binario_iminente": {"type": "noul", "instructions": "Is there a binary event in `contexto.eventos_proximos`?"},
        "recomendacao": {"type": "choice", "instructions": "Given all fields, which action best fits `posicao_usuario.horizonte`?", "criteria": {"compra": "Open long", "venda": "Close", "hold": "Wait"}},
    }


# Singleton para reuso (evita reconstruir a cada call)
QUESTIONS = build_questions()
