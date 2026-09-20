"""Composer — combina Scores com pesos + gates Noul/Confidence em código."""
from __future__ import annotations
from typing import Any
import pathlib, yaml

# pesos default (fallback se weights.yaml ausente)
DEFAULT_WEIGHTS = {"tendencia": 0.30, "fundamentos": 0.25, "sentimento": 0.15, "timing_inv": 0.15, "risco_inv": 0.15}
DEFAULT_THRESHOLDS = {"compra": 0.62, "venda": 0.38}
DEFAULT_GATES = {"risco_excessivo": 0.70, "evento_binario_iminente": 0.65, "informacao_insuficiente": 0.68, "confidence_min": 0.60}

def _load_weights() -> tuple[dict, dict, dict]:
    p = pathlib.Path(__file__).with_name("weights.yaml")
    if p.exists():
        data = yaml.safe_load(p.read_text())
        return data.get("weights", DEFAULT_WEIGHTS), data.get("thresholds", DEFAULT_THRESHOLDS), data.get("gates", DEFAULT_GATES)
    return DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS, DEFAULT_GATES

WEIGHTS, THRESHOLDS, GATES = _load_weights()

def _norm(score: float, levels: int) -> float:
    return max(0.0, min(1.0, score / (levels - 1)))

def _get(obj: Any, key: str, default=None):
    """Suporta obj dict-like ou objeto typesafe-sdk (atributos)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def compose(answers: dict[str, Any], ticker: str = "") -> dict[str, Any]:
    """
    answers: dict com chaves tendencia_tecnica, qualidade_fundamentalista, risco_volatilidade,
             sentimento_noticia, timing_momentum, risco_excessivo, informacao_insuficiente,
             evento_binario_iminente, recomendacao
    Cada answer pode ser objeto SDK (com .score/.noul/.choice/.confidence/.probabilities) ou dict de teste.
    Retorna saida tipada.
    """
    def score_of(k, levels):
        a = answers.get(k)
        s = _get(a, "score")
        if s is None:
            # fallback para dict raw de teste
            s = _get(a, "value", 2.0)
        return float(s), levels

    # Scores
    tend_s, _ = score_of("tendencia_tecnica", 5)
    fund_s, _ = score_of("qualidade_fundamentalista", 5)
    risco_s, _ = score_of("risco_volatilidade", 4)
    sent_s, _ = score_of("sentimento_noticia", 5)
    timing_s, _ = score_of("timing_momentum", 5)

    # Nouls
    def noul_of(k):
        a = answers.get(k)
        v = _get(a, "noul")
        if v is None:
            v = _get(a, "value", 0.0)
        return float(v)
    risco_excessivo = noul_of("risco_excessivo")
    info_insuf = noul_of("informacao_insuficiente")
    evento_bin = noul_of("evento_binario_iminente")

    # Choice
    rec = answers.get("recomendacao", {})
    choice = _get(rec, "choice", "hold")
    if isinstance(choice, str):
        choice = choice.lower()
    confidence = float(_get(rec, "confidence", 0.5) or 0.5)
    probabilities = _get(rec, "probabilities", {"compra": 0.33, "venda": 0.33, "hold": 0.34})

    # Normalização
    timing_buy = 1.0 - _norm(timing_s, 5)  # oversold (0) -> 1.0
    risco_inv = 1.0 - _norm(risco_s, 4)

    weighted = (
        WEIGHTS["tendencia"] * _norm(tend_s, 5)
        + WEIGHTS["fundamentos"] * _norm(fund_s, 5)
        + WEIGHTS["sentimento"] * _norm(sent_s, 5)
        + WEIGHTS["timing_inv"] * timing_buy
        + WEIGHTS["risco_inv"] * risco_inv
    )

    if weighted >= THRESHOLDS["compra"]:
        raw = "compra"
    elif weighted <= THRESHOLDS["venda"]:
        raw = "venda"
    else:
        raw = "hold"

    # Gates soberanos (Confidence-gated routing + Noul)
    motivo_gate = None
    if risco_excessivo > GATES["risco_excessivo"]:
        final, motivo_gate = "hold", f"risco_excessivo noul={risco_excessivo:.2f} > {GATES['risco_excessivo']}"
    elif evento_bin > GATES["evento_binario_iminente"]:
        final, motivo_gate = "hold", f"evento_binario_iminente noul={evento_bin:.2f} > {GATES['evento_binario_iminente']}"
    elif info_insuf > GATES["informacao_insuficiente"]:
        final, motivo_gate = "hold", f"informacao_insuficiente noul={info_insuf:.2f} > {GATES['informacao_insuficiente']}"
    elif confidence < GATES["confidence_min"]:
        final, motivo_gate = "hold", f"confidence {confidence:.2f} < {GATES['confidence_min']}"
    elif choice != raw and confidence > 0.75:
        final, motivo_gate = "hold", f"divergência choice={choice} vs raw={raw} com confidence alto"
    else:
        final = raw

    justificativa = (
        f"Tendência {tend_s:.1f}/4, fundamentos {fund_s:.1f}/4, sentimento {sent_s:.1f}/4, "
        f"timing {timing_s:.1f}/4, risco {risco_s:.1f}/3 | weighted={weighted:.2f} raw={raw} -> final={final}"
    )
    if motivo_gate:
        justificativa += f" | gate: {motivo_gate}"

    return {
        "ticker": ticker,
        "recomendacao": final,
        "recomendacao_raw": raw,
        "weighted": round(weighted, 3),
        "confidence": round(confidence, 3),
        "probabilidades": probabilities,
        "scores": {
            "tendencia_tecnica": tend_s,
            "qualidade_fundamentalista": fund_s,
            "risco_volatilidade": risco_s,
            "sentimento_noticia": sent_s,
            "timing_momentum": timing_s,
        },
        "gates": {
            "risco_excessivo": risco_excessivo,
            "informacao_insuficiente": info_insuf,
            "evento_binario_iminente": evento_bin,
        },
        "choice_original": choice,
        "justificativa": justificativa,
        "motivo_gate": motivo_gate,
        "disclaimer": "Conteúdo educacional. Não constitui recomendação personalizada (Res. CVM 20). Decisão final é do investidor.",
    }
