# Próximos Passos — Plano de Rollout Jev (ADK gemini-3.8-flash × Typesafe)

## Goal
Levar o Jev do estado atual (100% mock verde) para **live validado, interface testada e pronto para deploy**, sem quebrar as 12 unit + 10 e2e mock já verdes. Este plano é o checklist executável após o `GEMINI_MODEL=gemini-3.8-flash` já parametrizado.

## Success Criteria
- [ ] `pytest -m e2e --env=live -k petr4_swing` passa com `GOOGLE_API_KEY` + `TYPESAFE_API_KEY` reais: `model startswith jev-`, `probabilidades` soma 1, `Fontes:` aparecem.
- [ ] `pytest -m e2e --env=mock` continua 10 passed / 1 skipped (live) / 2 web skipped sem playwright; após `playwright install`, `tests/e2e/test_e2e_web.py` passa headless (ou skip documentado).
- [ ] `adk web --port 8000` manual: "vale comprar PETR4?" retorna em <8s `Recomendação: HOLD`, `confidence`, `Fontes` e `CVM`; `adk run jev_conversacional "oi"` não chama `call_jev_trader`.
- [ ] CI verde com marker `e2e` e artefato `report.html`; sem segredo vazado em log.
- [ ] Decisão de modelo fechada: `gemini-3.8-flash` validado ou fallback registrado.

## Context And Current Facts

**Onde estamos (verificado 2026-09-20):**
- `.venv` Python 3.11 ADK 1.18.0 + `typesafe-sdk 0.7.0` + `yfinance`; `GEMINI_MODEL` já em `jev_conversacional/.env` e `agent.py` (`load_dotenv` + `os.getenv("GEMINI_MODEL","gemini-3.8-flash")`); smoke `root_agent.model == gemini-3.8-flash` OK.
- `tests/`: 12 unit passed; `tests/e2e/`: 10 passed / 1 skipped live / 2 skipped web (playwright não instalado) em `--env=mock`; `tests/fixtures/golden/petr4_hold_evento.json` valida gate `evento_binario`.
- `jev_trader` (SystemOne 9 perguntas fan-out, composite `weights.yaml`) e `tools/jev_trader_tool.py` com mock `hold 0.62 gate 0.72` — live só com `TYPESAFE_API_KEY`.
- `adk web` dev-only (não prod) e `adk run` documentados em `https://adk.dev/get-started/python/` e `https://adk.dev/runtime/web-interface/`; `MemoryService` InMemory dev vs MemoryBank prod em `https://adk.dev/sessions/memory/`.

**Gaps abertos (maior risco primeiro):**
1. `gemini-3.8-flash` pode não existir no catálogo Gemini — `LlmAgent` falharia no primeiro `Runner.run_async` live.
2. Playwright não instalado → camada web nunca exercitada.
3. Live nunca rodado ponta-a-ponta com as chaves já inseridas (usuário inseriu `GOOGLE_API_KEY` + `TYPESAFE_API_KEY` mas E2E live não executado).
4. Sem CI gate formal; sem decisão de deploy (Cloud Run vs Vertex AI Agent Engine).

## Constraints And Non-goals

**Constraints:**
- Não sobrescrever `.env` (chaves já inseridas); qualquer edição usa `edit` com `find` exato.
- `adk web` é dev-only; deploy prod não é `adk web`.
- `pytest` reutiliza `pyproject.toml` existente; não criar segundo harness.
- Chaves nunca em log ou snapshot; modo mock deve continuar sem custo.

**Non-goals:**
- `VertexAiMemoryBankService` (requer GCP Project), load test, pixel-perfect visual test, A2A entre orgs.

## Key Decisions

| # | Decisão | Recomendação | Alternativa rejeitada | Por quê |
|---|---------|--------------|----------------------|---------|
| 1 | **Validação live primeiro** | Rodar `pytest -m e2e --env=live -k petr4` antes de qualquer outro trabalho | Instalar playwright primeiro | Se `gemini-3.8-flash` inexistir, todo E2E web será sobre modelo errado; falha deve ser a mais barata. |
| 2 | **Playwright** | `uv pip install --python .venv/bin/python pytest-playwright --no-cache` + `.venv/bin/playwright install chromium` | Cypress | `pytest-playwright` já integra com `pytest -m e2e` e `adk web` porta efêmera; Cypress é segundo runner. |
| 3 | **CI gate** | `pytest -m "not e2e"` + `pytest -m e2e --env=mock` no CI; `live` manual com `secrets` | Só unit | Mock garante CI verde sem custo; live valida contrato real sem bloquear merge. |
| 4 | **Deploy** | `adk web` (dev local) + `adk deploy` → Cloud Run **ou** Vertex AI Agent Engine (escolher após live) | FastAPI custom sem Runner | `Runner`/`SessionService`/`MemoryService` já prontos no ADK; FastAPI duplicaria runtime. |
| 5 | **Fallback modelo** | Se `gemini-3.8-flash` 404, registrar `GEMINI_MODEL=gemini-2.0-flash` com aviso e manter `.env.example` com `3.8-flash` como desejado | Hard-fail | Preserva intenção do usuário, mas não bloqueia rollout; opt anterior hard-coded quebrava sem alternativa. |

## Recommended Approach

### Ordem (menor risco de rework)
```
1. Live smoke (gemini-3.8-flash × jev-latest)  → decide se modelo é válido
2. Playwright install + web E2E                → fecha camada interface
3. CI gate (mock)                             → garante regressão
4. Manual adk web smoke (humano)              → enxerga UX real
5. Deploy prod (escolha Cloud Run vs Agent Engine)
```

### Passo 1 — Live smoke (5 min)
```bash
.venv/bin/python -m pytest tests/e2e/test_e2e_runner.py::test_modo_live_chama_jev_real -v --env=live -s
# espera: model startswith jev- , sum(prob)≈1
.venv/bin/python -m pytest tests/e2e/test_e2e_runner.py -v --env=live -k petr4
```
Se falhar com `Model not found: gemini-3.8-flash` → editar `GEMINI_MODEL` para `gemini-2.0-flash` e documentar em `docs/e2e.md` como fallback, mantendo `3.8-flash` como param desejado.

### Passo 2 — Playwright
```bash
uv pip install --python .venv/bin/python pytest-playwright --no-cache
.venv/bin/playwright install chromium
.venv/bin/python -m pytest tests/e2e/test_e2e_web.py -v --env=mock
# esperado: 1 passed (seletores ADK) + 1 skipped (sem GOOGLE_API_KEY real)
```

### Passo 3 — CI gate
Adicionar em CI:
```yaml
- run: uv run pytest tests/test_jev_trader.py tests/test_conversacional_adk.py -q
- run: uv run pytest tests/e2e -m e2e --env=mock -q --html=report.html
```

### Passo 4 — Manual adk web
```bash
.venv/bin/adk web --port 8000 &
# http://localhost:8000 → selecione jev_conversacional → "vale comprar PETR4 pra swing?"
# esperado: Recomendação HOLD, confidence, Fontes, CVM em <8s
.venv/bin/adk run jev_conversacional "oi"   # não deve chamar call_jev_trader
```

### Passo 5 — Deploy
- Opção A **Cloud Run**: `gcloud run deploy jev --source . --set-env-vars GOOGLE_API_KEY=...,TYPESAFE_API_KEY=...`
- Opção B **Vertex AI Agent Engine**: requer `GOOGLE_CLOUD_PROJECT` + `VertexAiMemoryBankService` (MemoryBank) — ver `https://adk.dev/sessions/memory/`.

## Work Plan

| Fase | Entregável | Comando / Arquivo | Dep |
|------|-----------|-------------------|-----|
| **1 — Live validation** | Log `jev-*` + confirmação `gemini-3.8-flash` | `pytest -m e2e --env=live -k petr4 -s` ; se 404, `edit` `GEMINI_MODEL` e `docs/e2e.md` | — |
| **2 — Interface install** | `pytest-playwright` + chromium + `test_e2e_web` verde | `uv pip install ... pytest-playwright`, `playwright install chromium`, `pytest tests/e2e/test_e2e_web.py` | 1 |
| **3 — CI** | Pipeline verde mock + artefato | `pytest -m "not e2e"` + `pytest -m e2e --env=mock --html=report.html` | 2 |
| **4 — Smoke manual** | Check `adk web`/`adk run` humano | `adk web --port 8000` + `adk run` | 1 |
| **5 — Deploy** | URL prod + escolha Cloud Run vs Agent Engine | `adk deploy` (doc `https://adk.dev/deploy/`) | 3,4 |

Cada fase é verificável isoladamente; 1 e 2 podem rodar em paralelo após live decidir modelo.

## Validation Plan

- **Fase 1 — Live:** `pytest tests/e2e/test_e2e_runner.py::test_modo_live_chama_jev_real --env=live -s` mostra `model=jev-1.x.x`, `ticker=PETR4`, `sum(prob)≈1`. Se `GOOGLE_API_KEY` inválida, skip com mensagem `live only` — não é falha.
- **Fase 2 — Web:** `pytest tests/e2e/test_e2e_web.py::test_web_adk_dev_ui_seletores --env=mock -v` → `1 passed` (conteúdo "Agent"); `test_web_chat_flow_mock` fica `skipped` sem chave real — esperado.
- **Fase 3 — CI:** `pytest -q` 12 passed + `pytest -m e2e --env=mock -q` 10 passed / 3 skipped, `report.html` gerado, nenhum log contém `AQ.Ab8...` ou `apikey_2212...`.
- **Fase 4 — Manual:** screenshot do `adk web` com bolha `Recomendação: HOLD` + `CVM` legível.
- **Fase 5 — Deploy:** `curl https://<cloud-run-url>/health` 200 e `POST /run` retorna `disclaimer`.

**Maior risco:** `gemini-3.8-flash` inexistente. Mitigação: fallback `gemini-2.0-flash` + aviso no `Validation Plan`; não bloqueia fases 2-4.

## Risks / Rollback

| Risco | Mitigação |
|-------|-----------|
| `gemini-3.8-flash` 404 | Fallback `GEMINI_MODEL=gemini-2.0-flash` em `agent.py` (`os.getenv` já tem default); documentar no `docs/e2e.md` |
| `.env` sobrescrito | `edit` com `find` exato + `cp .env .env.bak` antes |
| `adk web` DOM muda | `test_e2e_web` usa seletores resilientes (`textarea`, `button:has-text("Send")`); marcado `skip` se porta não sobe |
| Playwright sem deps CI | `playwright install --with-deps` no job; se falhar, `pytest -m "not e2e"` continua gate |
| `yfinance` offline | `get_market_data` fallback mock já testado |

**Rollback:** `git checkout -- jev_conversacional/agent.py jev_conversacional/.env.example` + `GEMINI_MODEL=gemini-2.0-flash` volta ao flash estável; `pip uninstall pytest-playwright` remove web layer.

## Open Questions

- Q1 — `gemini-3.8-flash` é alias exato ou deve ser `models/gemini-3.8-flash` / `gemini-3.8-flash-latest`? Validar no Passo 1 logs.
- Q2 — Deploy prod: Cloud Run (simples) vs Vertex AI Agent Engine (MemoryBank gerenciado)? Escolher após Passo 3 com time de infra.

## Sources

- https://adk.dev/get-started/python/ — `adk create/run/web`, `GOOGLE_API_KEY` em `.env`, `root_agent` model
- https://adk.dev/sessions/memory/ — `InMemoryMemoryService` vs `VertexAiMemoryBankService` vs `RAG`, `load_memory`/`add_session_to_memory`
- https://adk.dev/runtime/web-interface/ — `adk web --port 8000` dev-only, seleção de agente
- https://adk.dev/evaluate/ — avaliação E2E
- https://adk.dev/api-reference/python/ — referência
- https://docs.typesafe.ai/introduction/quickstart — `jev-latest`, 9 perguntas fan-out
- Repo local: `jev_conversacional/agent.py` (GEMINI_MODEL), `tests/e2e/*.py` (10 mock passed), `pyproject.toml` (marker e2e), `docs/plans/2026-09-20-*.md`

---
*Plano elaborado após inspeção de workspace e docs ADK/Typesafe em 2026-09-20. Aguardar aprovação para executar.*
