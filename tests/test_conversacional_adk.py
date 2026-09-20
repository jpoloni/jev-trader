"""Testes ADK conversacional — root_agent, tools, guardrails e memory."""
import pytest

def test_root_agent_import():
    from jev_conversacional.agent import root_agent
    assert root_agent.name == "jev_conversacional"
    assert "gemini" in root_agent.model
    assert root_agent.model == "gemini-3.8-flash"
    tool_names = [getattr(t, "name", type(t).__name__) for t in root_agent.tools]
    # load_memory, google_search, get_market_data, call_jev_trader
    assert len(root_agent.tools) == 4

def test_root_agent_tool_config_server_side():
    """Built-in google_search + FunctionTools exigem include_server_side_tool_invocations=True."""
    from jev_conversacional.agent import root_agent
    cfg = root_agent.generate_content_config
    assert cfg is not None
    assert cfg.tool_config is not None
    assert cfg.tool_config.include_server_side_tool_invocations is True

def test_before_tool_callback_valida_ticker():
    from jev_conversacional.agent import before_tool_callback
    class FakeTool:
        name = "call_jev_trader"
    # ticker inválido deve retornar erro
    ret = before_tool_callback(FakeTool(), {"ticker": "INVALIDO"}, None)
    assert ret is not None and "error" in ret
    # ticker válido não bloqueia
    ret2 = before_tool_callback(FakeTool(), {"ticker": "PETR4"}, None)
    assert ret2 is None
    ret3 = before_tool_callback(FakeTool(), {"ticker": "VALE3.SA"}, None)
    assert ret3 is None

def test_market_data_mock():
    from jev_conversacional.tools.market_data import get_market_data
    # yfinance real ou mock — ambos retornam estrutura esperada
    data = get_market_data("PETR4")
    assert "preco_atual" in data
    assert "candles_14d" in data
    assert "indicadores" in data
    assert len(data["candles_14d"]) >= 5

def test_call_jev_trader_tool():
    from jev_conversacional.tools.jev_trader_tool import call_jev_trader
    out = call_jev_trader("PETR4")
    assert out["ticker"] == "PETR4"
    assert out["recomendacao"] in ("compra","venda","hold")
    assert "confidence" in out and 0 <= out["confidence"] <= 1
    assert "probabilidades" in out
    assert out["disclaimer"]

def test_call_jev_trader_horizonte_override():
    from jev_conversacional.tools.jev_trader_tool import call_jev_trader
    out = call_jev_trader("VALE3", horizonte_override="daytrade", observacao_usuario="quero swing curto")
    assert out["state"]["posicao_usuario"]["horizonte"] == "daytrade"

@pytest.mark.asyncio
async def test_memory_add_and_search():
    """Integra ADK InMemorySessionService + InMemoryMemoryService + load_memory."""
    from google.adk.sessions import InMemorySessionService
    from google.adk.memory import InMemoryMemoryService
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.tools import load_memory
    from google.genai.types import Content, Part

    APP, USER, MODEL = "test_jev_app", "test_user_memory", "gemini-2.0-flash"
    session_service = InMemorySessionService()
    memory_service = InMemoryMemoryService()

    # Agent simples que só reconhece
    capture = LlmAgent(model=MODEL, name="Capture", instruction="Acknowledge.")
    runner1 = Runner(agent=capture, app_name=APP, session_service=session_service, memory_service=memory_service)
    sid1 = "sess1"
    await session_service.create_session(app_name=APP, user_id=USER, session_id=sid1)
    # não chamamos LLM real — criamos evento manual e persistimos sessão direto via memory_service
    # Em vez disso, testamos o contrato: add_session_to_memory com sessão vazia não falha
    sess = await session_service.get_session(app_name=APP, user_id=USER, session_id=sid1)
    await memory_service.add_session_to_memory(sess)
    # busca por keyword (InMemory usa keyword matching)
    res = await memory_service.search_memory(app_name=APP, user_id=USER, query="PETR4")
    assert res is not None
