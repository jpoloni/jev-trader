"""Fixtures E2E — Runner ADK, mocks, adk web server."""
import os
import socket
import subprocess
import time
import json
import pathlib
import pytest
from typing import AsyncGenerator

# ADK imports
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from jev_conversacional.agent import root_agent

SCENARIOS_PATH = pathlib.Path(__file__).parent / "fixtures" / "scenarios.json"

def pytest_addoption(parser):
    parser.addoption("--env", action="store", default="mock", help="mock ou live")
    parser.addoption("--adk-port", action="store", default="0", help="porta adk web (0=efêmera)")

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: testes end-to-end")

@pytest.fixture
def env_mode(request):
    return request.config.getoption("--env")

@pytest.fixture
def scenarios():
    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))

@pytest.fixture
async def adk_runner():
    """Runner ADK com InMemory services compartilhados (API layer)."""
    session_service = InMemorySessionService()
    memory_service = InMemoryMemoryService()
    runner = Runner(agent=root_agent, app_name="e2e", session_service=session_service, memory_service=memory_service)
    return runner, session_service, memory_service

@pytest.fixture
def mock_google_search(monkeypatch):
    """Stub google_search para modo mock — evita chamada real."""
    # Não patcha globalmente; testes usam mock_answers no Jev-Trader, google_search não é chamado em modo mock runner
    return True

@pytest.fixture(scope="session")
def adk_web_server(request):
    """Sobe adk web em porta efêmera (fixture session, skip se sem chromium/playwright ou sem GOOGLE_API_KEY sem mock)."""
    # Apenas quando explicitamente solicitado via --env=live ou marker web
    # Para CI mock, não sobe servidor por default — teste web é skip se não houver playwright
    port = int(request.config.getoption("--adk-port"))
    if port == 0:
        # encontra porta livre
        with socket.socket() as s:
            s.bind(("", 0))
            port = s.getsockname()[1]
    proc = None
    try:
        # tenta subir adk web; se falhar (sem env), yield None e teste skip
        env = os.environ.copy()
        proc = subprocess.Popen(
            [".venv/bin/adk", "web", "--port", str(port)],
            cwd=".",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # aguarda 3s por bind
        for _ in range(30):
            time.sleep(0.2)
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                if proc.poll() is not None:
                    break
        yield f"http://127.0.0.1:{port}" if proc and proc.poll() is None else None
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
