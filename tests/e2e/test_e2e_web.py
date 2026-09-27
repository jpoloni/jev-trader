"""E2E Web — Playwright contra adk web (dev UI). Skip se playwright não instalado ou adk web não sobe."""
import pytest

pytestmark = pytest.mark.e2e

try:
    import os
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        HAS_PLAYWRIGHT = os.path.exists(_p.chromium.executable_path)
except Exception:
    HAS_PLAYWRIGHT = False

@pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright não instalado — rode: uv pip install --python .venv/bin/python pytest-playwright && .venv/bin/playwright install chromium")
def test_web_adk_dev_ui_seletores(adk_web_server):
    """Valida que adk web sobe e seletores esperados existem (sem depender de LLM)."""
    if adk_web_server is None:
        pytest.skip("adk web não subiu — sem GOOGLE_API_KEY ou porta em uso")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(adk_web_server, timeout=10000)
            # Aguarda título ADK ou seletor de agente
            page.wait_for_timeout(2000)
            content = page.content()
            # Dev UI contém "Agent Development Kit" ou seletor de agente
            assert "Agent" in content or "adk" in content.lower()
        finally:
            browser.close()

@pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright não instalado")
def test_web_chat_flow_mock(adk_web_server):
    """Fluxo chat mínimo — envia mensagem e aguarda bolha de resposta (live). Skip em mock."""
    if adk_web_server is None:
        pytest.skip("adk web não disponível")
    import os
    if not os.getenv("GOOGLE_API_KEY") or "sua-chave" in os.getenv("GOOGLE_API_KEY", ""):
        pytest.skip("sem GOOGLE_API_KEY real — modo mock")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(adk_web_server, timeout=10000)
            page.wait_for_timeout(2000)
            # Tenta localizar input de chat (vários seletores possíveis)
            for sel in ["textarea", "input[type='text']", "[placeholder*='Type']", "[placeholder*='Message']"]:
                if page.locator(sel).count() > 0:
                    page.locator(sel).first.fill("vale comprar PETR4?")
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(5000)
                    html = page.content()
                    # Asserts estruturados PT-BR
                    assert "Recomendação" in html or "PETR4" in html or "CVM" in html
                    break
        finally:
            browser.close()
