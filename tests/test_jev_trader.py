"""Testes duráveis Jev-Trader — cobrem state, questions, composer e client mock."""
from jev_trader.state import build_state, validate_state
from jev_trader.questions import build_questions, QUESTIONS
from jev_trader.composer import compose
from jev_trader.client import call_jev_trader

def test_state_canonical():
    s = build_state(ticker="petr4", preco_atual=38.42, noticias_7d=["notícia A"], posicao_usuario={"perfil_risco": "moderado", "horizonte": "swing"})
    assert s["ativo"]["ticker"] == "PETR4"
    assert s["ativo"]["bolsa"] == "B3"
    assert s["restricoes"]["disclaimer"]
    assert validate_state(s) == []

def test_questions_structure():
    qs = build_questions()
    # 9 perguntas obrigatórias
    assert set(qs) == {"tendencia_tecnica","qualidade_fundamentalista","risco_volatilidade","sentimento_noticia","timing_momentum","risco_excessivo","informacao_insuficiente","evento_binario_iminente","recomendacao"}
    # backticks em instructions (ancoragem ADK/Typesafe)
    for k in ["tendencia_tecnica", "risco_volatilidade", "recomendacao"]:
        instr = getattr(qs[k], "instructions", qs[k].get("instructions", "")) if isinstance(qs[k], dict) else getattr(qs[k], "instructions", "")
        assert "`" in instr or "mercado" in instr or "posicao_usuario" in instr

def test_composer_hold_por_confidence_baixa():
    mock = {
        "tendencia_tecnica": {"score": 4.0},
        "qualidade_fundamentalista": {"score": 4.0},
        "risco_volatilidade": {"score": 0.0},
        "sentimento_noticia": {"score": 4.0},
        "timing_momentum": {"score": 0.0},
        "risco_excessivo": {"noul": 0.1},
        "informacao_insuficiente": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.1},
        "recomendacao": {"choice": "compra", "confidence": 0.45, "probabilities": {"compra": 0.7, "venda": 0.1, "hold": 0.2}},
    }
    out = compose(mock, ticker="PETR4")
    # weighted alto daria compra, mas confidence baixa força hold (gate)
    assert out["recomendacao"] == "hold"
    assert "confidence" in out["motivo_gate"]

def test_composer_hold_por_gate_evento():
    mock = {
        "tendencia_tecnica": {"score": 4.0},
        "qualidade_fundamentalista": {"score": 4.0},
        "risco_volatilidade": {"score": 0.0},
        "sentimento_noticia": {"score": 4.0},
        "timing_momentum": {"score": 0.0},
        "risco_excessivo": {"noul": 0.1},
        "informacao_insuficiente": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.85},
        "recomendacao": {"choice": "compra", "confidence": 0.80, "probabilities": {"compra": 0.7, "venda": 0.1, "hold": 0.2}},
    }
    out = compose(mock, ticker="VALE3")
    assert out["recomendacao"] == "hold"
    assert "evento_binario" in out["motivo_gate"]

def test_composer_compra_quando_tudo_favoravel():
    mock = {
        "tendencia_tecnica": {"score": 4.0},
        "qualidade_fundamentalista": {"score": 4.0},
        "risco_volatilidade": {"score": 0.0},
        "sentimento_noticia": {"score": 4.0},
        "timing_momentum": {"score": 0.0},
        "risco_excessivo": {"noul": 0.1},
        "informacao_insuficiente": {"noul": 0.1},
        "evento_binario_iminente": {"noul": 0.1},
        "recomendacao": {"choice": "compra", "confidence": 0.75, "probabilities": {"compra": 0.7, "venda": 0.1, "hold": 0.2}},
    }
    out = compose(mock, ticker="ITUB4")
    assert out["recomendacao"] == "compra"
    assert out["weighted"] >= 0.62

def test_call_jev_trader_mock():
    mock = {
        "tendencia_tecnica": {"score": 2.0},
        "qualidade_fundamentalista": {"score": 2.0},
        "risco_volatilidade": {"score": 2.0},
        "sentimento_noticia": {"score": 2.0},
        "timing_momentum": {"score": 2.0},
        "risco_excessivo": {"noul": 0.2},
        "informacao_insuficiente": {"noul": 0.2},
        "evento_binario_iminente": {"noul": 0.2},
        "recomendacao": {"choice": "hold", "confidence": 0.65, "probabilities": {"compra": 0.2, "venda": 0.2, "hold": 0.6}},
    }
    out = call_jev_trader(ticker="PETR4", mock_answers=mock)
    assert out["ticker"] == "PETR4"
    assert out["recomendacao"] in ("compra","venda","hold")
    assert out["disclaimer"]
    assert out["model"] == "jev-mock"
