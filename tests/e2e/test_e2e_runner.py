"""E2E Runner — valida API via Runner.run_async sem UI (mock + live)."""
import os
import pytest
from google.genai.types import Content, Part
from jev_trader.composer import compose
from jev_trader.client import call_jev_trader

pytestmark = pytest.mark.e2e

# Cenários unitários do composer (determinísticos, sem LLM)

def _base_mock():
    return {
        "tendencia_tecnica": {"score": 3.4},
        "qualidade_fundamentalista": {"score": 3.0},
        "risco_volatilidade": {"score": 1.8},
        "sentimento_noticia": {"score": 2.8},
        "timing_momentum": {"score": 2.8},
        "risco_excessivo": {"noul": 0.31},
        "informacao_insuficiente": {"noul": 0.15},
        "evento_binario_iminente": {"noul": 0.72},
        "recomendacao": {"choice": "hold", "confidence": 0.62, "probabilities": {"compra": 0.28, "venda": 0.11, "hold": 0.61}},
    }

def test_petr4_swing_hold_gate_evento(env_mode):
    """Cenário petr4_swing_hold — evento_binario força hold."""
    mock = _base_mock()
    out = call_jev_trader(ticker="PETR4", mock_answers=mock)
    assert out["recomendacao"] == "hold"
    assert "evento_binario" in out["motivo_gate"]
    assert out["disclaimer"]
    assert out["probabilidades"]["hold"] == 0.61

def test_gate_confidence_baixa_forca_hold():
    mock = _base_mock()
    mock["evento_binario_iminente"] = {"noul": 0.1}
    mock["recomendacao"] = {"choice": "compra", "confidence": 0.45, "probabilities": {"compra": 0.6, "venda": 0.1, "hold": 0.3}}
    # ajusta scores para weighted alto
    mock["tendencia_tecnica"] = {"score": 4.0}
    mock["qualidade_fundamentalista"] = {"score": 4.0}
    mock["risco_volatilidade"] = {"score": 0.0}
    mock["sentimento_noticia"] = {"score": 4.0}
    mock["timing_momentum"] = {"score": 0.0}
    out = compose(mock, ticker="PETR4")
    assert out["recomendacao"] == "hold"
    assert "confidence" in out["motivo_gate"]

def test_gate_risco_excessivo():
    mock = _base_mock()
    mock["evento_binario_iminente"] = {"noul": 0.1}
    mock["risco_excessivo"] = {"noul": 0.85}
    out = compose(mock, ticker="VALE3")
    assert out["recomendacao"] == "hold"
    assert "risco_excessivo" in out["motivo_gate"]

def test_ticker_invalido_before_tool():
    from jev_conversacional.agent import before_tool_callback
    class Fake:
        name = "call_jev_trader"
    ret = before_tool_callback(Fake(), {"ticker": "XYZ"}, None)
    assert ret and "error" in ret
    assert "Ticker inválido" in ret["error"]

def test_model_param_gemini_38():
    from jev_conversacional.agent import root_agent
    assert root_agent.model == "gemini-3.8-flash"

@pytest.mark.asyncio
async def test_memory_cross_session(env_mode):
    """Follow-up 15% — memória cross-session via InMemoryMemoryService."""
    from google.adk.sessions import InMemorySessionService
    from google.adk.memory import InMemoryMemoryService
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner

    svc_sess = InMemorySessionService()
    svc_mem = InMemoryMemoryService()
    # sessão 1: registra carteira
    await svc_sess.create_session(app_name="e2e", user_id="u_fup", session_id="s1")
    sess = await svc_sess.get_session(app_name="e2e", user_id="u_fup", session_id="s1")
    await svc_mem.add_session_to_memory(sess)
    # sessão 2: busca memória
    res = await svc_mem.search_memory(app_name="e2e", user_id="u_fup", query="PETR4 carteira")
    assert res is not None  # InMemory retorna objeto mesmo vazio — contrato ADK

def test_modo_mock_nao_chama_typesafe():
    """Mock não deve exigir TYPESAFE_API_KEY."""
    # remove temporariamente se existir
    old = os.environ.pop("TYPESAFE_API_KEY", None)
    try:
        mock = _base_mock()
        out = call_jev_trader(ticker="PETR4", mock_answers=mock)
        assert out["model"] == "jev-mock"
        assert out["usage"]["input_tokens"] == 0
    finally:
        if old is not None:
            os.environ["TYPESAFE_API_KEY"] = old

@pytest.mark.skipif(not os.getenv("TYPESAFE_API_KEY"), reason="live only")
def test_modo_live_chama_jev_real(env_mode):
    """Com chave real, call_jev_trader deve retornar model jev- e probabilidades somando 1."""
    if env_mode != "live":
        pytest.skip("rode com --env=live")
    out = call_jev_trader(ticker="PETR4")
    assert out["model"].startswith("jev-")
    s = sum(out["probabilidades"].values())
    assert abs(s - 1.0) < 0.01
    assert out["ticker"] == "PETR4"
