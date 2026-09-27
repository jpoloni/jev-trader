"""Testes unitários e de regressão para o Composer (pesos, gates e horizontes)."""
import pytest
from jev_trader.composer import compose, HORIZON_PROFILES, _norm


def test_horizon_weights_sum_to_one():
    """Valida propriedade fundamental: a soma dos pesos de cada perfil deve ser 1.0."""
    for h, profile in HORIZON_PROFILES.items():
        w = profile["weights"]
        total = sum(w.values())
        assert abs(total - 1.0) < 1e-5, f"Pesos para o horizonte '{h}' não somam 1.0: {total}"


def test_score_norm_bounds():
    """Valida normalização de scores."""
    assert _norm(0.0, 5) == 0.0
    assert _norm(4.0, 5) == 1.0
    assert _norm(2.0, 5) == 0.5
    assert _norm(-1.0, 5) == 0.0  # clamp
    assert _norm(10.0, 5) == 1.0  # clamp


def test_compose_clean_compra():
    """Cenário ideal de compra sem nenhum gate acionado."""
    answers = {
        "tendencia_tecnica": {"score": 4.0},       # 4/4 = 1.0
        "qualidade_fundamentalista": {"score": 4.0},# 4/4 = 1.0
        "risco_volatilidade": {"score": 0.0},       # 0/3 -> risco_inv = 1.0
        "sentimento_noticia": {"score": 4.0},       # 4/4 = 1.0
        "timing_momentum": {"score": 0.0},          # oversold (0) -> timing_buy = 1.0
        "risco_excessivo": {"noul": 0.1},
        "informacao_insuficiente": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.1},
        "recomendacao": {
            "choice": "compra",
            "confidence": 0.85,
            "probabilities": {"compra": 0.85, "venda": 0.05, "hold": 0.10},
        },
    }
    out = compose(answers, ticker="PETR4", horizonte="swing")
    assert out["ticker"] == "PETR4"
    assert out["weighted"] == 1.0
    assert out["recomendacao_raw"] == "compra"
    assert out["recomendacao"] == "compra"
    assert out["motivo_gate"] is None


def test_compose_clean_venda():
    """Cenário ideal de venda sem nenhum gate acionado."""
    answers = {
        "tendencia_tecnica": {"score": 0.0},       # 0.0
        "qualidade_fundamentalista": {"score": 0.0},# 0.0
        "risco_volatilidade": {"score": 3.0},       # max risco -> risco_inv = 0.0
        "sentimento_noticia": {"score": 0.0},       # 0.0
        "timing_momentum": {"score": 4.0},          # overbought -> timing_buy = 0.0
        "risco_excessivo": {"noul": 0.2},
        "informacao_insuficiente": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.1},
        "recomendacao": {
            "choice": "venda",
            "confidence": 0.85,
            "probabilities": {"compra": 0.05, "venda": 0.85, "hold": 0.10},
        },
    }
    out = compose(answers, ticker="VALE3", horizonte="swing")
    assert out["weighted"] == 0.0
    assert out["recomendacao_raw"] == "venda"
    assert out["recomendacao"] == "venda"
    assert out["motivo_gate"] is None


def test_gate_risco_excessivo():
    """Gate de risco excessivo força recomendação para hold."""
    answers = {
        "tendencia_tecnica": {"score": 4.0},
        "qualidade_fundamentalista": {"score": 4.0},
        "risco_volatilidade": {"score": 0.0},
        "sentimento_noticia": {"score": 4.0},
        "timing_momentum": {"score": 0.0},
        "risco_excessivo": {"noul": 0.85},  # > 0.70 gate
        "informacao_insuficiente": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.1},
        "recomendacao": {"choice": "compra", "confidence": 0.80},
    }
    out = compose(answers, ticker="PETR4", horizonte="swing")
    assert out["recomendacao_raw"] == "compra"
    assert out["recomendacao"] == "hold"
    assert "risco_excessivo" in out["motivo_gate"]


def test_gate_evento_binario():
    """Gate de evento binário iminente (balanço, etc.) força hold."""
    answers = {
        "tendencia_tecnica": {"score": 4.0},
        "qualidade_fundamentalista": {"score": 4.0},
        "risco_volatilidade": {"score": 0.0},
        "sentimento_noticia": {"score": 4.0},
        "timing_momentum": {"score": 0.0},
        "risco_excessivo": {"noul": 0.2},
        "evento_binario_iminente": {"noul": 0.75},  # > 0.65 gate
        "informacao_insuficiente": {"noul": 0.1},
        "recomendacao": {"choice": "compra", "confidence": 0.80},
    }
    out = compose(answers, ticker="PETR4", horizonte="swing")
    assert out["recomendacao_raw"] == "compra"
    assert out["recomendacao"] == "hold"
    assert "evento_binario_iminente" in out["motivo_gate"]


def test_gate_informacao_insuficiente():
    """Gate de informação insuficiente força hold."""
    answers = {
        "tendencia_tecnica": {"score": 4.0},
        "qualidade_fundamentalista": {"score": 4.0},
        "risco_volatilidade": {"score": 0.0},
        "sentimento_noticia": {"score": 4.0},
        "timing_momentum": {"score": 0.0},
        "risco_excessivo": {"noul": 0.2},
        "evento_binario_iminente": {"noul": 0.1},
        "informacao_insuficiente": {"noul": 0.80},  # > 0.68 gate
        "recomendacao": {"choice": "compra", "confidence": 0.80},
    }
    out = compose(answers, ticker="PETR4", horizonte="swing")
    assert out["recomendacao_raw"] == "compra"
    assert out["recomendacao"] == "hold"
    assert "informacao_insuficiente" in out["motivo_gate"]


def test_gate_confidence_minima():
    """Gate de confiança mínima: se confidence for baixa, força hold."""
    answers = {
        "tendencia_tecnica": {"score": 4.0},
        "qualidade_fundamentalista": {"score": 4.0},
        "risco_volatilidade": {"score": 0.0},
        "sentimento_noticia": {"score": 4.0},
        "timing_momentum": {"score": 0.0},
        "risco_excessivo": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.1},
        "informacao_insuficiente": {"noul": 0.1},
        "recomendacao": {"choice": "compra", "confidence": 0.45},  # < 0.60 gate swing
    }
    out = compose(answers, ticker="PETR4", horizonte="swing")
    assert out["recomendacao_raw"] == "compra"
    assert out["recomendacao"] == "hold"
    assert "confidence" in out["motivo_gate"]


def test_horizon_daytrade_thresholds():
    """Valida limiar de compra e gates calibrados para day trade (threshold 0.58)."""
    # Score intermediário ~0.60
    answers = {
        "tendencia_tecnica": {"score": 3.0},       # 3/4 = 0.75
        "qualidade_fundamentalista": {"score": 2.0},# 2/4 = 0.50
        "risco_volatilidade": {"score": 1.0},       # 1 - 1/3 = 0.67
        "sentimento_noticia": {"score": 2.0},       # 2/4 = 0.50
        "timing_momentum": {"score": 1.0},          # 1 - 1/4 = 0.75
        "risco_excessivo": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.1},
        "informacao_insuficiente": {"noul": 0.1},
        "recomendacao": {"choice": "compra", "confidence": 0.70},
    }
    out_dt = compose(answers, ticker="ITUB4", horizonte="daytrade")
    # Day trade com threshold 0.58 classifica compra
    assert out_dt["weighted"] >= 0.58
    assert out_dt["recomendacao"] == "compra"


def test_divergence_gate_triggers_hold():
    """Se raw for compra mas o LLM escolheu venda com alta confiança (>0.75), diverge -> hold."""
    answers = {
        "tendencia_tecnica": {"score": 4.0},
        "qualidade_fundamentalista": {"score": 4.0},
        "risco_volatilidade": {"score": 0.0},
        "sentimento_noticia": {"score": 4.0},
        "timing_momentum": {"score": 0.0},
        "risco_excessivo": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.1},
        "informacao_insuficiente": {"noul": 0.1},
        "recomendacao": {"choice": "venda", "confidence": 0.88},  # divergência gritante
    }
    out = compose(answers, ticker="PETR4", horizonte="swing")
    assert out["recomendacao_raw"] == "compra"
    assert out["recomendacao"] == "hold"
    assert "divergência" in out["motivo_gate"]
