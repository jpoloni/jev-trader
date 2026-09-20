"""Cliente Typesafe — 1 chamada fan-out (9 perguntas)."""
from __future__ import annotations
import os
from typing import Any
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
) -> dict[str, Any]:
    """Monta State, valida, chama Typesafe (ou mock) e compõe."""
    if state_override is not None:
        state = state_override
    else:
        state = build_state(ticker=ticker, preco_atual=preco_atual, noticias_7d=noticias_7d, posicao_usuario=posicao_usuario)

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
            raise RuntimeError("TYPESAFE_API_KEY não definida no ambiente (.env).")
        client = TypeSafeClient()
        resp = client.system_one(state=state, questions=QUESTIONS, model="jev-latest")
        # resp.answers é dict de objetos tipados
        answers = resp.answers  # type: ignore
        model = getattr(resp, "model", "jev-latest")
        usage = getattr(resp, "usage", {})

    out = compose(answers, ticker=ticker)
    out["model"] = model
    out["usage"] = usage
    out["state"] = state
    return out


if __name__ == "__main__":
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="PETR4")
    p.add_argument("--horizonte", default="swing")
    args = p.parse_args()
    # demo mock (sem chave)
    mock = {
        "tendencia_tecnica": {"score": 3.4},
        "qualidade_fundamentalista": {"score": 3.0},
        "risco_volatilidade": {"score": 1.5},
        "sentimento_noticia": {"score": 2.8},
        "timing_momentum": {"score": 2.2},
        "risco_excessivo": {"noul": 0.31},
        "informacao_insuficiente": {"noul": 0.12},
        "evento_binario_iminente": {"noul": 0.72},
        "recomendacao": {"choice": "hold", "confidence": 0.62, "probabilities": {"compra": 0.28, "venda": 0.11, "hold": 0.61}},
    }
    print(json.dumps(call_jev_trader(ticker=args.ticker, mock_answers=mock), ensure_ascii=False, indent=2))
