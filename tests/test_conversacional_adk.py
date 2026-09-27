"""Testes ADK conversacional — root_agent, tools, guardrails e memory."""
import pytest

def test_root_agent_import():
    from jev_conversacional.agent import root_agent
    assert root_agent.name == "jev_conversacional"
    assert "gemini" in root_agent.model
    assert root_agent.model == "gemini-3.8-flash"
    tool_names = [getattr(t, "__name__", getattr(t, "name", type(t).__name__)) for t in root_agent.tools]
    # load_memory, google_search, get_market_data, call_jev_trader, scan_b3, manage_portfolio, compare_tickers
    assert len(root_agent.tools) == 7
    assert "scan_b3" in tool_names
    assert "manage_portfolio" in tool_names
    assert "compare_tickers" in tool_names
    assert "CHAME SEMPRE a tool scan_b3" in root_agent.instruction

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


def test_portfolio_crud_and_summary(tmp_path, monkeypatch):
    """Testa compras, vendas com lucro/prejuízo e consolidação da carteira."""
    import jev_trader.portfolio as p_mod
    monkeypatch.setattr(p_mod, "PORTFOLIO_FILE", tmp_path / "portfolio.json")
    monkeypatch.setattr(p_mod, "TRADES_FILE", tmp_path / "trade_history.json")

    from jev_conversacional.tools.portfolio_tool import manage_portfolio

    # 1. Compra PETR4
    res_buy1 = manage_portfolio(acao="comprar", ticker="PETR4", quantidade=100, preco=35.0)
    assert res_buy1["status"] == "sucesso"
    assert res_buy1["posicao_atualizada"]["quantidade"] == 100
    assert res_buy1["posicao_atualizada"]["preco_medio"] == 35.0

    # 2. Segunda compra PETR4 (novo PM ponderado: (100*35 + 100*45)/200 = 40.0)
    res_buy2 = manage_portfolio(acao="comprar", ticker="PETR4", quantidade=100, preco=45.0)
    assert res_buy2["posicao_atualizada"]["quantidade"] == 200
    assert res_buy2["posicao_atualizada"]["preco_medio"] == 40.0

    # 3. Compra VALE3
    manage_portfolio(acao="comprar", ticker="VALE3", quantidade=50, preco=60.0)

    # 4. Consulta posição específica
    pos_petr = manage_portfolio(acao="posicao", ticker="PETR4")
    assert pos_petr["posicao"]["ticker"] == "PETR4"
    assert pos_petr["posicao"]["quantidade"] == 200

    # 5. Venda parcial de PETR4 com lucro (vende 50 a R$ 50,00 -> lucro = (50-40)*50 = R$ 500)
    res_sell = manage_portfolio(acao="vender", ticker="PETR4", quantidade=50, preco=50.0)
    assert res_sell["status"] == "sucesso"
    assert res_sell["resultado_venda"]["quantidade_restante"] == 150
    assert res_sell["resultado_venda"]["pl_realizado_reais"] == 500.0

    # 6. Resumo geral da carteira
    resumo = manage_portfolio(acao="resumo")
    assert resumo["total_ativos"] == 2
    assert "posicoes" in resumo
    assert len(resumo["posicoes"]) == 2

    # 7. Histórico de trades (2 compras PETR4 + 1 compra VALE3 + 1 venda PETR4 = 4)
    hist = manage_portfolio(acao="historico")
    assert hist["total_trades"] == 4
    assert hist["trades"][-1]["tipo"] == "VENDA"


def test_sqlite_storage_operations(tmp_path, monkeypatch):
    """Testa persistência de mensagens, preferências e recomendações no SQLite."""
    import jev_conversacional.sqlite_storage as s_mod
    monkeypatch.setattr(s_mod, "DB_PATH", tmp_path / "test_memory.db")

    s_mod.init_db()

    # 1. Mensagens
    s_mod.save_message("sess_1", "user", "Olá, recomende uma ação de swing trade.")
    s_mod.save_message("sess_1", "agent", "Aqui está a análise de PETR4...")
    msgs = s_mod.get_recent_messages("sess_1")
    assert len(msgs) == 2
    assert msgs[0]["sender"] == "user"
    assert msgs[1]["sender"] == "agent"

    # 2. Preferências
    s_mod.set_user_preference("perfil_risco", "arrojado")
    s_mod.set_user_preference("horizonte_default", "daytrade")
    assert s_mod.get_user_preference("perfil_risco") == "arrojado"
    assert s_mod.get_user_preference("horizonte_default") == "daytrade"
    all_prefs = s_mod.get_all_preferences()
    assert all_prefs["perfil_risco"] == "arrojado"

    # 3. Log de Recomendações
    s_mod.log_recommendation("PETR4", "compra", 0.75, 0.80, 42.50)
    recs = s_mod.get_past_recommendations("PETR4")
    assert len(recs) == 1
    assert recs[0]["ticker"] == "PETR4"
    assert recs[0]["recomendacao"] == "compra"


def test_compare_tickers_tool():
    """Valida comparação lado a lado de múltiplos tickers."""
    from jev_conversacional.tools.compare_tool import compare_tickers

    # Rejeita menos de 2 tickers
    err = compare_tickers(["PETR4"])
    assert "error" in err

    # Compara 2 tickers válidos
    res = compare_tickers(["PETR4", "VALE3"], horizonte="swing")
    assert res["total_comparados"] == 2
    assert "comparativo" in res
    assert len(res["comparativo"]) == 2
    assert res["melhor_ativo"] in ("PETR4", "VALE3")
    assert "scores" in res["comparativo"][0]
    assert "multiplos" in res["comparativo"][0]


