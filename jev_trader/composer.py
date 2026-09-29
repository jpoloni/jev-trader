"""Composer — combina Scores com pesos + gates Noul/Confidence em código."""
from __future__ import annotations
from typing import Any
import pathlib, yaml

# pesos default (fallback se weights.yaml ausente)
DEFAULT_WEIGHTS = {"tendencia": 0.30, "fundamentos": 0.25, "sentimento": 0.15, "timing_inv": 0.15, "risco_inv": 0.15}
DEFAULT_THRESHOLDS = {"compra": 0.62, "venda": 0.38}
DEFAULT_GATES = {"risco_excessivo": 0.70, "evento_binario_iminente": 0.65, "informacao_insuficiente": 0.68, "confidence_min": 0.60}

def _load_weights() -> tuple[dict, dict, dict]:
    """Perfil swing versionado em weights.yaml (fonte da verdade); defaults só se o arquivo faltar."""
    p = pathlib.Path(__file__).with_name("weights.yaml")
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
        return (
            {**DEFAULT_WEIGHTS, **(data.get("weights") or {})},
            {**DEFAULT_THRESHOLDS, **(data.get("thresholds") or {})},
            {**DEFAULT_GATES, **(data.get("gates") or {})},
        )
    return DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS, DEFAULT_GATES

# Swing (default global) vem do weights.yaml
WEIGHTS, THRESHOLDS, GATES = _load_weights()

# Perfis por horizonte — ajustam pesos e gates dinamicamente
HORIZON_PROFILES: dict[str, dict[str, Any]] = {
    "swing": {
        "weights": WEIGHTS,
        "thresholds": THRESHOLDS,
        "gates": GATES,
    },
    "daytrade": {
        "weights": {"tendencia": 0.35, "fundamentos": 0.10, "sentimento": 0.10, "timing_inv": 0.30, "risco_inv": 0.15},
        "thresholds": {"compra": 0.58, "venda": 0.35},
        "gates": {"risco_excessivo": 0.75, "evento_binario_iminente": 0.70, "informacao_insuficiente": 0.92, "confidence_min": 0.30},
    },
    "posicional": {
        "weights": {"tendencia": 0.20, "fundamentos": 0.35, "sentimento": 0.15, "timing_inv": 0.10, "risco_inv": 0.20},
        "thresholds": {"compra": 0.65, "venda": 0.40},
        "gates": {"risco_excessivo": 0.65, "evento_binario_iminente": 0.60, "informacao_insuficiente": 0.65, "confidence_min": 0.65},
    },
}

def normalize_horizonte(horizonte: str | None) -> str:
    """Mapeia texto livre para um perfil: 'swing (2-8 semanas)' -> swing, 'Day Trade' -> daytrade.

    Desconhecido ou vazio -> swing.
    """
    h = "".join(ch for ch in (horizonte or "").lower() if ch.isalnum())
    if h.startswith("day") or h.startswith("intraday"):
        return "daytrade"
    if h.startswith("posic") or h.startswith("position") or h.startswith("longo"):
        return "posicional"
    return "swing"

def _get_profile(horizonte: str | None) -> tuple[dict, dict, dict]:
    """Retorna (weights, thresholds, gates) para o horizonte dado."""
    p = HORIZON_PROFILES[normalize_horizonte(horizonte)]
    return p["weights"], p["thresholds"], p["gates"]

def _norm(score: float, levels: int) -> float:
    return max(0.0, min(1.0, score / (levels - 1)))

def _get(obj: Any, key: str, default=None):
    """Suporta obj dict-like ou objeto typesafe-sdk (atributos)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def compose(answers: dict[str, Any], ticker: str = "", horizonte: str | None = None) -> dict[str, Any]:
    """
    answers: dict com chaves tendencia_tecnica, qualidade_fundamentalista, risco_volatilidade,
             sentimento_noticia, timing_momentum, risco_excessivo, informacao_insuficiente,
             evento_binario_iminente, recomendacao
    Cada answer pode ser objeto SDK (com .score/.noul/.choice/.confidence/.probabilities) ou dict de teste.
    horizonte: 'swing'|'daytrade'|'posicional' — ajusta pesos e gates automaticamente.
    Retorna saida tipada.
    """
    # Seleciona perfil de pesos/gates para o horizonte
    w, t, g = _get_profile(horizonte)

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
    raw_conf = _get(rec, "confidence")
    confidence = 0.5 if raw_conf is None else float(raw_conf)  # 0.0 é valor válido, não "ausente"
    probabilities = _get(rec, "probabilities", {"compra": 0.33, "venda": 0.33, "hold": 0.34})

    # Normalização
    timing_buy = 1.0 - _norm(timing_s, 5)  # oversold (0) -> 1.0
    risco_inv = 1.0 - _norm(risco_s, 4)

    weighted = (
        w["tendencia"] * _norm(tend_s, 5)
        + w["fundamentos"] * _norm(fund_s, 5)
        + w["sentimento"] * _norm(sent_s, 5)
        + w["timing_inv"] * timing_buy
        + w["risco_inv"] * risco_inv
    )

    if weighted >= t["compra"]:
        raw = "compra"
    elif weighted <= t["venda"]:
        raw = "venda"
    else:
        raw = "hold"

    # Gates soberanos (Confidence-gated routing + Noul)
    motivo_gate = None
    if risco_excessivo > g["risco_excessivo"]:
        final, motivo_gate = "hold", f"risco_excessivo noul={risco_excessivo:.2f} > {g['risco_excessivo']}"
    elif evento_bin > g["evento_binario_iminente"]:
        final, motivo_gate = "hold", f"evento_binario_iminente noul={evento_bin:.2f} > {g['evento_binario_iminente']}"
    elif info_insuf > g["informacao_insuficiente"]:
        final, motivo_gate = "hold", f"informacao_insuficiente noul={info_insuf:.2f} > {g['informacao_insuficiente']}"
    elif confidence < g["confidence_min"]:
        final, motivo_gate = "hold", f"confidence {confidence:.2f} < {g['confidence_min']}"
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
        "horizonte": normalize_horizonte(horizonte),
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
        "limites_gates": dict(g),
        "choice_original": choice,
        "justificativa": justificativa,
        "motivo_gate": motivo_gate,
        "disclaimer": "Conteúdo educacional. Não constitui recomendação personalizada (Res. CVM 20). Decisão final é do investidor.",
    }
