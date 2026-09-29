"""Cliente Typesafe — 1 chamada fan-out (9 perguntas)."""
from __future__ import annotations
import os
import pathlib
from typing import Any
from dotenv import load_dotenv

# Carrega variáveis de ambiente (.env raiz e de jev_conversacional/.env)
load_dotenv()
load_dotenv(pathlib.Path(__file__).parent.parent / "jev_conversacional" / ".env")

from .state import build_state, validate_state
from .questions import QUESTIONS
from .composer import compose

try:
    from typesafe_sdk import TypeSafeClient  # type: ignore
    HAS_SDK = True
except Exception:
    HAS_SDK = False

def call_jev_trader(
    *,
    ticker: str,
    state_override: dict[str, Any] | None = None,
    # atalhos para construir State sem montar dict completo
    preco_atual: float | None = None,
    noticias_7d: list[str] | None = None,
    posicao_usuario: dict[str, Any] | None = None,
    mock_answers: dict[str, Any] | None = None,  # para testes sem API key
    horizonte: str | None = None,  # swing|daytrade|posicional
    nome: str | None = None,
    setor: str | None = None,
    fundamentos: dict[str, Any] | None = None,
    indicadores: dict[str, Any] | None = None,
    candles_14d: list[dict[str, Any]] | None = None,
    variacao_dia_pct: float | None = None,
) -> dict[str, Any]:
    """Monta State, valida, chama Typesafe (ou mock) e compõe."""
    if state_override is not None:
        state = state_override
    else:
        state = build_state(
            ticker=ticker,
            nome=nome,
            setor=setor,
            preco_atual=preco_atual,
            variacao_dia_pct=variacao_dia_pct,
            candles_14d=candles_14d,
            indicadores=indicadores,
            fundamentos=fundamentos,
            noticias_7d=noticias_7d,
            posicao_usuario=posicao_usuario,
        )

    errs = validate_state(state)
    if errs:
        raise ValueError(f"State inválido: {errs}")

    if mock_answers is not None:
        answers = mock_answers
        model = "jev-mock"
        usage = {"input_tokens": 0, "output_tokens": 0}
    else:
        if not HAS_SDK:
            raise RuntimeError("typesafe-sdk não instalado. Instale com pip install typesafe-sdk ou use mock_answers.")
        api_key = os.getenv("TYPESAFE_API_KEY")
        if not api_key:
            raise RuntimeError("TYPESAFE_API_KEY não definida no ambiente (.env). Adicione em jev_conversacional/.env ou exporte.")
        client = TypeSafeClient()
        resp = client.system_one(state=state, questions=QUESTIONS, model="jev-latest")
        # resp.answers é dict de objetos tipados
        answers = resp.answers  # type: ignore
        model = getattr(resp, "model", "jev-latest")
        usage = getattr(resp, "usage", {})

    # Extrai horizonte do state se não fornecido explicitamente
    if not horizonte and state_override:
        pos = state_override.get("posicao_usuario", {})
        horizonte = pos.get("horizonte", "swing")
    out = compose(answers, ticker=ticker, horizonte=horizonte)
    out["model"] = model
    
    # Ensure usage is a JSON-serializable dict
    if hasattr(usage, "model_dump"):
        out["usage"] = usage.model_dump()
    elif hasattr(usage, "__dict__"):
        out["usage"] = usage.__dict__
    else:
        out["usage"] = dict(usage) if isinstance(usage, dict) else {}
        
    out["state"] = state
    return out


if __name__ == "__main__":
    import argparse
    import json
    from .cli_ui import render_ticker_card, set_color_enabled

    p = argparse.ArgumentParser(description="Jev-Trader — Análise analítica de ativo B3 (Typesafe)")
    p.add_argument("--ticker", default="PETR4", help="Ticker do ativo (ex: PETR4, VALE3)")
    p.add_argument("--horizonte", default="swing", help="Horizonte de investimento (swing, daytrade, posicional)")
    p.add_argument("--live", action="store_true", help="Força modo ao vivo chamando Typesafe API real (requer TYPESAFE_API_KEY)")
    p.add_argument("--mock", action="store_true", help="Usa respostas simuladas determinísticas (sem API key)")
    p.add_argument("--json", action="store_true", help="Emite resultado apenas como JSON puro (para scripts/pipes)")
    p.add_argument("--no-color", action="store_true", help="Desativa cores ANSI")
    args = p.parse_args()

    if args.no_color:
        set_color_enabled(False)

    ticker = args.ticker.upper().strip()

    # Tenta buscar dados de mercado reais via yfinance se disponível
    preco_atual = None
    var_dia = None
    candles = None
    indicadores = None
    fundamentos = None
    nome = None
    setor = None
    noticias = None
    try:
        from jev_conversacional.tools.market_data import get_market_data
        md = get_market_data(ticker)
        preco_atual = md.get("preco_atual")
        var_dia = md.get("variacao_dia_pct")
        candles = md.get("candles_14d")
        indicadores = md.get("indicadores")
        fundamentos = md.get("fundamentos")
        nome = md.get("nome")
        setor = md.get("setor")
        noticias = md.get("noticias_recentes")
    except Exception:
        pass

    if not noticias:
        try:
            from .news_feed import get_news_feed
            noticias = get_news_feed(ticker, limit=4)
        except Exception:
            noticias = ["(Sem notícias disponíveis)"]

    state = build_state(
        ticker=ticker,
        nome=nome,
        setor=setor,
        preco_atual=preco_atual,
        variacao_dia_pct=var_dia,
        candles_14d=candles,
        indicadores=indicadores,
        fundamentos=fundamentos,
        noticias_7d=noticias,
        posicao_usuario={"tem_posicao": False, "perfil_risco": "moderado", "horizonte": args.horizonte},
    )


    if args.live:
        if not os.getenv("TYPESAFE_API_KEY"):
            raise RuntimeError("Flag --live informada, mas TYPESAFE_API_KEY não foi encontrada no ambiente nem em jev_conversacional/.env.")
        use_mock = False
    elif args.mock:
        use_mock = True
    else:
        # Default: se TYPESAFE_API_KEY existir, roda live; caso contrário roda mock
        use_mock = not bool(os.getenv("TYPESAFE_API_KEY"))

    mock_payload = None
    if use_mock:
        from .mock_answers import mock_answers_for_ticker
        mock_payload = mock_answers_for_ticker(ticker)

    res = call_jev_trader(ticker=ticker, state_override=state, mock_answers=mock_payload)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render_ticker_card(res))


