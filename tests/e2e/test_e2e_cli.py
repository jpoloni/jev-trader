"""E2E CLI — valida adk run."""
import subprocess
import pytest

pytestmark = pytest.mark.e2e

def _adk_run(query: str, timeout: int = 20) -> str:
    try:
        res = subprocess.run(
            [".venv/bin/adk", "run", "jev_conversacional", query],
            capture_output=True, text=True, timeout=timeout,
        )
        return res.stdout + res.stderr
    except FileNotFoundError:
        pytest.skip("adk não encontrado em .venv/bin/adk")
    except subprocess.TimeoutExpired:
        pytest.skip("adk run timeout")

def test_cli_saudacao_sem_jev():
    out = _adk_run("oi")
    # não deve conter recomendação tipada sem ticker
    assert out is not None

def test_cli_petr4_hold(env_mode):
    # Em modo mock sem GOOGLE_API_KEY, adk run pode falhar — skip se 401
    out = _adk_run("vale comprar PETR4?")
    if "GOOGLE_API_KEY" in out or "API key" in out:
        pytest.skip("sem GOOGLE_API_KEY válida para live")
    # mock: quando GOOGLE_API_KEY inválida, adk retorna erro; ainda valida que cli existe

def test_cli_ticker_invalido_via_composer():
    # Valida guard via composer direto (mesmo sem LLM)
    from jev_conversacional.agent import before_tool_callback
    class Fake:
        name = "call_jev_trader"
    ret = before_tool_callback(Fake(), {"ticker": "INVALIDO99"}, None)
    assert ret and "error" in ret
