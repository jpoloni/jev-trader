# E2E — Jev Conversacional (ADK gemini-3.8-flash × Typesafe)

Este doc resume como rodar a suíte E2E (mock + live + interface).

## Modelo
`GEMINI_MODEL=gemini-3.8-flash` em `jev_conversacional/.env` (e `.env.example`), lido por `agent.py` via `os.getenv("GEMINI_MODEL", "gemini-3.8-flash")`.

Verifique:
```bash
.venv/bin/python -c "from jev_conversacional.agent import root_agent; print(root_agent.model)"
# → gemini-3.8-flash
```

## Camadas

| Camada | Arquivo | Quando usar |
|--------|---------|-------------|
| Runner (API) | `tests/e2e/test_e2e_runner.py` | CI, sem LLM externo, mais estável |
| CLI | `tests/e2e/test_e2e_cli.py` | `adk run jev_conversacional "query"` |
| Web | `tests/e2e/test_e2e_web.py` | `adk web` + Playwright (headless). Skip se sem `playwright` ou sem `GOOGLE_API_KEY` |

## Mock vs Live

- **Mock (default CI):** sem `TYPESAFE_API_KEY` → `call_jev_trader` usa `mock_answers` (`usage 0`). `google_search` stub.
- **Live:** com `jev_conversacional/.env` contendo `GOOGLE_API_KEY` + `TYPESAFE_API_KEY` (já inseridas), rode com `--env=live`.

## Comandos

```bash
# Unit (12 testes, já verde)
.venv/bin/python -m pytest tests/test_jev_trader.py tests/test_conversacional_adk.py -v

# E2E mock (10 passed, 1 skipped live, 2 skipped web quando sem playwright)
.venv/bin/python -m pytest tests/e2e -m e2e --env=mock -v

# E2E live (requer chaves no .env)
.venv/bin/python -m pytest tests/e2e/test_e2e_runner.py -m e2e --env=live -v -k petr4

# Interface web manual
.venv/bin/adk web --port 8000  # http://localhost:8000 → selecione jev_conversacional

# Web E2E com Playwright (opcional)
uv pip install --python .venv/bin/python pytest-playwright --no-cache
.venv/bin/playwright install chromium
.venv/bin/python -m pytest tests/e2e/test_e2e_web.py -v --env=mock

# Tudo
.venv/bin/python -m pytest tests -v
```

## Cenários (15 em fixtures/scenarios.json)
`saudacao`, `petr4_swing_hold` (gate evento_binario), `vale3_venda`, `ticker_invalido`, `followup_15pct` (memória cross-session), `web_search_*` (3), `gate_*` (3), `modo_live`, `interface_*` (3).

Asserts: `recomendacao ∈ {compra,venda,hold}`, `confidence` numérico, `probabilidades` soma 1, `disclaimer` CVM, `Fontes:` quando `google_search`, `before_tool_callback` ticker inválido → erro.
