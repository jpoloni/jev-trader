# Jev Conversacional (Google ADK) — Spec do Agente Chat com Memória Persistente, Web Search e Jev-Trader como Subagente

## Goal
Revisar a spec `2026-09-20-jev-conversacional` para **arquitetura Google**: implementar o **Jev Conversacional** sobre o **Agent Development Kit (ADK) Python**, mantendo o **Jev-Trader (System One, Typesafe)** como subagente especialista `compra/venda/hold`. O ADK provê `Session`/`State`, `MemoryService`, `Runner`, `AgentTool`/`FunctionTool` e `google_search` grounding; o Jev-Trader continua sendo 1 chamada `POST /v1/systemone` (`jev-latest`, 9 perguntas paralelas) encapsulada num `FunctionTool`. Código permanece no controle.

## Success Criteria
- [ ] Projeto ADK criado via `pip install google-adk` + `adk create jev_conversacional` com `agent.py` contendo `root_agent = Agent(model="gemini-flash-latest", ...)` executável via `adk run` e `adk web --port 8000`.
- [ ] Conversa PT-BR orquestrada por `Runner` com `InMemorySessionService` (dev) / `VertexAi*` (prod) + `MemoryService`: usuário diz "sou moderado, swing, tenho PETR4 8%" e em nova `Session` o `load_memory` recupera sem re-perguntar (recall >85% em 20 diálogos golden).
- [ ] Web search automático via ADK `google_search` (Grounding) + `FunctionTool` de cotação (yfinance/Brapi) com cache 15 min/ticker; toda recomendação cita fontes buscadas.
- [ ] `call_jev_trader` é `FunctionTool` que monta `State` canônico (6 chaves), chama `typesafe-sdk` (`TypeSafeClient.system_one`) com 9 perguntas e roda `composer.py` (pesos+ gates); retorno tipado `{recomendacao, confidence, probabilidades, scores, gates, model, usage, sources}` ao LLM orquestrador.
- [ ] Guardrails ADK: `before_model_callback` bloqueia recomendação sem `call_jev_trader` quando intent=recomendacao; `before_tool_callback` valida `ticker` e `confidence<0.60 => hold` com linguagem cautelosa + disclaimer CVM obrigatório.
- [ ] Deploy `adk web` (dev) e `adk deploy` / Cloud Run / Vertex AI Agent Engine (prod) com `GOOGLE_API_KEY` em `.env`; logs `jev-1.13.0` + `usage` + `probabilities` auditáveis.

## Context And Current Facts

**Herança — specs aprovadas:**
- `docs/plans/2026-09-20-jev-trader.md`: State objeto 6 chaves (`ativo`, `mercado` com `candles_14d`+ indicadores calculados em código, `fundamentos`, `contexto`, `posicao_usuario`, `restricoes`), 9 perguntas (5 `Score` + 3 `Noul` + 1 `Choice`), instructions em inglês com backticks `` `campo.path` ``, Composer com pesos `weights.yaml` (`>=0.62 compra / <=0.38 venda`) e gates `Noul>0.70` + `confidence<0.60 => hold`. Typesafe: `POST https://api.typesafe.ai/v1/systemone`, `model: jev-latest`, response `{model: "jev-1.13.0", answers: {id: {choice/score/noul, probabilities, confidence, legend}}, usage}`, `Choice` sem ordem, `Score` ordenado fracionário, `Noul` 0..1, todos veem mesmo `state` em paralelo, `confidence=(n*peak-1)/(n-1)`, padrões Fan-out / Composite Scoring / Confidence-gated Routing.
- `docs/plans/2026-09-20-jev-conversacional.md`: agente chat System Two orquestra memória + web search + Jev-Trader subagente; v1 propunha SQLite+Chroma e Tavily (agora substituídos por ADK).

**Google ADK — fatos verificados em https://adk.dev:**
- **Instalação ADK Python**: `pip install google-adk` (Python 3.10+), `adk create my_agent` cria `my_agent/agent.py` + `.env` + `__init__.py`; `root_agent = Agent(model="gemini-flash-latest", name, description, instruction, tools=[...])` é o único elemento obrigatório; `GOOGLE_API_KEY` em `.env` (`echo 'GOOGLE_API_KEY="..."' > .env`).
- **Execução**: `adk run my_agent` (CLI) e `adk web --port 8000` (UI de dev, não para produção; rodar do diretório pai de `my_agent/`).
- **Componentes centrais**: `Tool` (habilidades além de conversa — APIs, search, `AgentTool`), `Session`/`State` (contexto de uma conversa: `Events` + scratchpad `State`; `State` com escopos `app:`, `user:`, `temp:`), `Memory` (`MemoryService` para conhecimento de longo prazo cross-session, distinto de `State`), `Runner` (engine que orquestra fluxo por `Events`), `Callbacks` e `Code Execution`.
- **MemoryService**: interface `BaseMemoryService` com `add_session_to_memory(session)`, `add_events_to_memory`, `add_memory(MemoryEntry)`, `search_memory(query)`; implementações Python: `InMemoryMemoryService` (keyword, sem persistência, default), `VertexAiMemoryBankService` (extrai memórias significativas via LLM e consolida, busca semântica, requer Agent Engine em Google Cloud), `VertexAiRagMemoryService` (Knowledge Engine, vector search sobre corpus completo). Tool `load_memory` consulta `MemoryService`. `Runner` recebe `session_service` + `memory_service` compartilhados entre sessões.
- **Tools ADK**: `FunctionTool` (função Python), `AgentTool` (outro agente como tool), built-ins e MCP/OpenAPI; suporte a long-running tools e `before_model_callback`/`before_tool_callback`.
- **Grounding**: `Google Search Grounding` dedicado (`grounding/google_search_grounding`) — alternativa nativa ao Tavily/Brave.
- **Multi-agente**: `Agent Team` tutorial (delegação via `AgentTool` ou LLM transfer), `Session State` para personalização, e workflows `Sequential`/`Parallel`/`Loop`/`Custom`.

**Workspace:** `/Users/jpoloni/dev/jev` greenfield; sem código ADK prévio. ADK será a espinha dorsal; Jev-Trader permanece como serviço Typesafe externo.

## Constraints And Non-goals

**Constraints:**
- ADK Python como framework obrigatório; LLM orquestrador = `gemini-flash-latest` (default ADK) via `GOOGLE_API_KEY`; Jev-Trader permanece System One externo — `gemini` nunca "chuta" `compra/venda` sem `FunctionTool`.
- `Session` (curto prazo) vs `MemoryService` (longo prazo) respeitados: `State` (`user:perfil_risco`, `user:pct_carteira`, `temp:last_state`) vive na sessão; `MemoryService` persiste fatos curados cross-session (profile/portfolio/decision).
- LGPD + CVM: `MemoryService` opt-in, `DELETE`/`migrate` via API; logs Jev com `user_id` hasheado; toda mensagem com recomendação tem disclaimer educacional fixo; nunca executa ordem.
- 1 chamada Typesafe por recomendação (fan-out); `google_search` com `before_tool_callback` para rate-limit/cache; custo/latência controlados.
- Chat PT-BR, `instructions` Jev-Trader em inglês (maior acurácia Typesafe).

**Non-goals (v1 ADK):**
- Deploy prod completo em Vertex AI (fica como fase final), voz/live (`adk live`), fine-tuning `Gemma`, A2A entre organizações, app mobile nativo.

## Key Decisions

| # | Decisão | Recomendação (ADK) | Alternativa rejeitada | Por quê |
|---|---------|-------------------|----------------------|---------|
| 1 | **Framework** | ADK Python (`google-adk`) com `Agent` + `Runner` | LangGraph / CrewAI / código puro sem ADK | ADK já entrega `Session`/`State`/`MemoryService`/`Runner`/`Callbacks` e dev UI; reimplementar seria duplicar o que o tutorial Agent Team + Memory já resolve. |
| 2 | **Orquestrador vs Jev-Trader** | `root_agent` (`LlmAgent` Gemini) orquestra; Jev-Trader é `FunctionTool` `call_jev_trader` (não `AgentTool` separado) — handler monta State e chama Typesafe | `AgentTool` com um `JevTraderAgent` LlmAgent | Jev-Trader não é LLM — é API HTTP determinística; `FunctionTool` é o mapeamento correto (doc: `FunctionTool`, `AgentTool` para agente LLM). Mantém `composer.py` em código. |
| 3 | **Memória persistente** | Dev: `InMemoryMemoryService` + `InMemorySessionService`; Prod: `VertexAiMemoryBankService` (memórias consolidadas via LLM) — híbrido: `State (user:)` para fato quente + `load_memory` para recall | SQLite+Chroma custom da spec anterior | ADK Memory já tem `add_session_to_memory` + `search_memory` + `load_memory` tool + consolidação semântica (Memory Bank). Evita reinventar retrieval e persiste automaticamente cross-session. Spec anterior marcada como fallback se GCP indisponível. |
| 4 | **Web search** | ADK `google_search` grounding (built-in) + `FunctionTool` `get_market_data(ticker)` (yfinance/Brapi) para cotação/candles determinísticos; `before_tool_callback` com cache 15 min | Tavily/Brave custom | `google_search` é o grounding oficial ADK (doc `grounding/google_search_grounding`), já integrado ao `Runner` com citações; Tavily vira fallback só se grounding indisponível. |
| 5 | **Estado ADK vs State Typesafe** | ADK `Session State` (`user:perfil_risco`, `user:portfolio_PETR4`, `temp:last_jev_state`) alimenta o `State` JSON Typesafe (6 chaves) na tool | Um único JSON global | Separação preserva semântica ADK (State é scratchpad por sessão com escopos) e evita confundir com `state` Typesafe (payload da API). Tool faz a tradução. |
| 6 | **Workflows ADK** | `root_agent` simples com tools; `ParallelAgent` opcional para `memory recall || web search` em paralelo se latência exigir | `SequentialAgent` com 3 etapas fixas sempre | Para v1, root_agent com function calling já paraleliza tools; `ParallelAgent` entra só se medição mostrar ganho. Evita complexidade prematura. |
| 7 | **Segurança** | `before_model_callback` (bloqueia recomendação sem tool) + `before_tool_callback` (valida ticker, `confidence` gating, injeta disclaimer) | Validação só no prompt | Callbacks são o mecanismo ADK oficial para guardrails (tutorial Step 5/6), executam em código antes do LLM/tool, garantem CVM mesmo se prompt for jailbreakado. |
| 8 | **Deploy** | Dev: `adk web` / `adk run`; Prod: `adk deploy` → Cloud Run ou Vertex AI Agent Engine (com `VertexAiMemoryBankService`) | FastAPI custom sem ADK runtime | `adk deploy` + `Runner` já cuidam de sessão, eventos e observabilidade; FastAPI só como wrapper se precisar expor REST fora do ADK. |

## Recommended Approach

### 1. Arquitetura ADK

```
[User PT-BR] -> [ADK Runner] -> [root_agent (LlmAgent gemini-flash-latest)]
                              |-> SessionService (InMemory / VertexAi)  -> Session/State (user:, temp:)
                              |-> MemoryService (InMemory dev / MemoryBank prod) <-> load_memory / add_session_to_memory
                              |-> Tools: google_search (grounding) + get_market_data(ticker) + call_jev_trader(ticker)
                              |   └─ call_jev_trader -> monta State Typesafe (6 chaves) -> TypeSafeClient.system_one -> composer (pesos+gates)
                              |-> Callbacks: before_model_callback (guard), before_tool_callback (ticker/cache/gating)
                              |-> Resposta PT-BR (template + Gemini paráfrase + fontes + disclaimer)
```

**Analogia ADK:** `Session/State` = memória curta da conversa; `MemoryService` = arquivo pesquisável de longo prazo; `Runner` = motor de eventos; `google_search` = grounding oficial.

### 2. Estrutura de Projeto ADK

```bash
pip install google-adk typesafe-sdk yfinance
adk create jev_conversacional
# gera:
jev_conversacional/
  agent.py         # root_agent + tools + callbacks
  tools/
    jev_trader_tool.py   # call_jev_trader FunctionTool
    market_data.py       # get_market_data FunctionTool
  jev_trader/            # reuso da spec anterior (state.py, questions.py, composer.py, weights.yaml)
  .env             # GOOGLE_API_KEY="..."  + TYPESAFE_API_KEY="..."
  __init__.py
```

**`jev_conversacional/agent.py` (esqueleto validado com quickstart ADK + Memory):**

```python
from google.adk.agents.llm_agent import Agent
from google.adk.tools import load_memory  # tool oficial de memória
from google.adk.tools import google_search  # grounding (import exato conforme versão ADK)
from tools.jev_trader_tool import call_jev_trader
from tools.market_data import get_market_data

# Guardrails
def before_model_callback(ctx, llm_request):
    # Bloqueia recomendação se intent==recomendacao e call_jev_trader não foi invocado
    # Retorna None para seguir, ou modifica llm_request para pedir esclarecimento
    return None

def before_tool_callback(tool, args, tool_context):
    # Valida ticker (regex ^[A-Z]{4}\d{1,2}$), aplica cache google_search 15min
    return None

root_agent = Agent(
    model="gemini-flash-latest",
    name="jev_conversacional",
    description="Assessor B3 educacional com memória persistente e Jev-Trader subagente",
    instruction=(
        "Você é o Jev Conversacional (PT-BR). "
        "Use <memoria> via load_memory e google_search quando necessário. "
        "Para qualquer pedido de compra/venda/hold com ticker, CHAME call_jev_trader. "
        "Nunca recomende sem chamar a tool. "
        "Após receber o JSON do Jev-Trader, explique em PT-BR com: Recomendação, Confiança, Por quê (scores), Riscos/Gates, Fontes e Disclaimer CVM fixo. "
        "Se confidence<0.60 ou gate>0.70, use linguagem cautelosa e ofereça acompanhamento."
    ),
    tools=[load_memory, google_search, get_market_data, call_jev_trader],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
)
```

**`tools/jev_trader_tool.py`:** `FunctionTool` que (1) lê ADK State (`user:perfil_risco`, `user:portfolio_*`) + memória via `tool_context.search_memory`, (2) chama `get_market_data` + `google_search` (ou recebe `contexto.noticias_7d` já buscado), (3) monta `State` canônico (`jev_trader/state.py`), (4) `TypeSafeClient().system_one(state, questions, model="jev-latest")`, (5) `composer.py` → JSON tipado ao LLM.

**ADK Runner (prod, Memory Bank):**

```python
from google.adk.sessions import InMemorySessionService  # dev
# from google.adk.sessions import VertexAiSessionService  # prod
from google.adk.memory import InMemoryMemoryService
# from google.adk.memory import VertexAiMemoryBankService  # prod (requer ADK[gcp] + Agent Engine)
from google.adk.runners import Runner

session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()  # trocar por VertexAiMemoryBankService em prod
runner = Runner(agent=root_agent, app_name="jev_app", session_service=session_service, memory_service=memory_service)
# ciclo: await runner.run_async(user_id, session_id, new_message)
# após sessão: await memory_service.add_session_to_memory(completed_session)
```

**ADK State (escopos):**
- `user:perfil_risco = "moderado"` , `user:horizonte = "swing"` , `user:portfolio_PETR4 = {"pct":8.5, "pm":35.0}`
- `temp:last_jev_state = {...}` (State Typesafe cacheado 5 min), `temp:last_recomendacao = {...}`
- `app:weights_version = "v1.0"` (config global)

### 3. Memory — mapeamento ADK

| Conceito spec anterior | ADK equivalente |
|------------------------|-----------------|
| `memories` SQLite+vector | `MemoryService` (`InMemoryMemoryService` dev / `VertexAiMemoryBankService` prod) |
| `conversations` | `Session` + `Events` (histórico por `session_id`) |
| `recall()` híbrido top-8 | `load_memory` tool + `search_memory(query)` via `tool_context` |
| `extract_and_upsert()` summarizer | `add_session_to_memory(session)` (Memory Bank extrai fatos significativos via LLM e consolida) + opcional `add_memory(MemoryEntry)` para fatos explícitos |
| `DELETE /users/{id}/memories` | `MemoryService` com expiração / `migrate` + `VertexAiMemoryBank` lifecycle |

**Fluxo memória ADK:**
1. Turno inicia → `root_agent` decide usar `load_memory` (ex.: ticker PETR4) → `Runner` injeta snippets relevantes no contexto.
2. Fim de sessão → `await memory_service.add_session_to_memory(completed_session)` → Memory Bank gera memórias.
3. Follow-up "e se eu aumentar para 15%?" → `load_memory` traz `portfolio_PETR4 8%` e decisão anterior `hold`.

### 4. Web Search — ADK Grounding

- Primário: `google_search` (ADK grounding) para `"{ticker} notícias 7 dias"`, `"{ticker} balanço"`, `"Ibovespa hoje"`. Retorna snippets com citações nativas.
- Complemento determinístico: `get_market_data(ticker)` → yfinance/Brapi para `preco_atual`, `variacao_dia_pct`, `candles_14d`, `rsi_14` (cálculo em código, não LLM).
- Cache: `before_tool_callback` verifica `temp:web:{ticker}:{date}` (ADK State) TTL 15 min antes de chamar `google_search`.

### 5. Jev-Trader Subagente — contrato inalterado

State 6 chaves, 9 perguntas, Composer pesos+gates, `TYPESAFE_API_KEY` em `.env` — agora encapsulado. `call_jev_trader` traduz ADK State → Typesafe State:

```python
state = {
  "ativo": {...}, "mercado": {...}, "fundamentos": {...},
  "contexto": {"noticias_7d": google_search_summary, "eventos_proximos": ..., "sentimento_mercado": ...},
  "posicao_usuario": {"pct_carteira": state.get("user:portfolio_PETR4.pct"), "perfil_risco": state.get("user:perfil_risco")},
  "restricoes": {"disclaimer": "Análise educacional, não é recomendação personalizada (CVM)"}
}
resp = TypeSafeClient().system_one(state=state, questions=QUESTIONS, model="jev-latest")
composer_output = compose(resp.answers)  # {recomendacao, confidence, probabilidades, scores, gates}
```

### 6. Fluxo de Conversa (ADK Events)

**Recomendação nova:**
```
User: "Vale comprar PETR4 pra swing?"  (Event user)
-> Runner -> root_agent (gemini) -> decide load_memory("PETR4 perfil") + google_search("PETR4 notícias 7d")
-> get_market_data("PETR4") -> State ADK atualizado
-> call_jev_trader(ticker="PETR4") -> POST Typesafe -> composer hold conf 0.62 gate evento_binario 0.72
-> root_agent gera PT-BR com Recomendação HOLD + Fontes (Reuters/Valor) + Disclaimer
-> Runner persiste Events na Session
-> (fim de sessão) memory_service.add_session_to_memory(session) -> memória consolidada
```

**Follow-up memória:** "E se eu aumentar para 15%?" → `load_memory` traz `portfolio 8%`, `call_jev_trader` com `pct_carteira=15` simulado → `risco_excessivo 0.78 => hold`.

### 7. Observabilidade ADK

- `adk web` mostra `Events`, `State` changes e tool calls em tempo real (dev).
- Logs: `user_id_hash`, `session_id`, `intent`, `jev_model`, `jev_confidence`, `web_queries`, `Runner` latência, `usage` Typesafe.
- Avaliação: `adk evaluate` (ADK Evaluation) sobre 20 diálogos golden; métricas `recall memória`, `hold por baixa confiança`, `citação de fontes`.

## Work Plan

| Fase | Entregável | Detalhe | Dep |
|------|-----------|---------|-----|
| **1 — Base ADK + Jev-Trader** | `adk create jev_conversacional` + `jev_trader/` | `pip install google-adk typesafe-sdk`, `agent.py` esqueleto, `.env` com `GOOGLE_API_KEY`+`TYPESAFE_API_KEY`, reuso `state.py/questions.py/composer.py/weights.yaml` da spec Jev-Trader; teste `adk run` com `get_current_time` mock. | — |
| **2 — Memory ADK** | `InMemoryMemoryService` + `load_memory` | Configurar `Runner` com `InMemorySessionService`/`InMemoryMemoryService` (dev) e `add_session_to_memory` pós-sessão; `test_memory_recall` com cenário Project Alpha adaptado para PETR4; validar `load_memory` em 2 sessions. | 1 |
| **3 — Web & Market Tools** | `google_search` + `get_market_data` | Integrar grounding ADK + `FunctionTool` yfinance/Brapi, `before_tool_callback` com cache `temp:web:*`; testes com mock `google_search`. | 1 |
| **4 — Subagente Tool** | `call_jev_trader` FunctionTool | Handler ADK que lê `tool_context.state` + `search_memory`, monta State Typesafe, chama Typesafe e roda composer; valida 9 chaves em `response.answers`. | 2,3 |
| **5 — Root Agent & Guardrails** | `root_agent` + callbacks | Prompt PT-BR, `before_model_callback` (bloqueia recomendação sem tool), `before_tool_callback` (valida ticker, gating `confidence`); `test_orchestrator` intent→tool. | 4 |
| **6 — Dev UI & API** | `adk web` + `API Server` | `adk web --port 8000` (dev) e `adk deploy` / Cloud Run (prod); expor `POST /chat` via ADK API Server se necessário. | 5 |
| **7 — Eval & Docs** | Golden conversations + `docs/jev-conversacional-adk.md` | 20 diálogos (5 cross-session, 5 follow-up simulação), `adk evaluate` + `scripts/eval_conversations.py`; README com `adk create/run/web` e Playground Typesafe. | 6 |

Fases 1-2 em paralelo; 3 depende de 1.

## Validation Plan

- **Unitário:**
  - `pytest test_memory.py` — após `add_session_to_memory` com "tenho PETR4 8% @35", `load_memory("PETR4")` em nova `Session` retorna snippet; `VertexAiMemoryBankService` (se instalado via `pip install google-adk[gcp]`) faz busca semântica.
  - `pytest test_web.py` — `google_search` mock retorna `noticias_7d` 3 bullets + `sources`; `before_tool_callback` cache hit não chama grounding.
  - `pytest test_jev_tool.py` — mock `TypeSafeClient.system_one` → `choice: hold, confidence 0.62`; `call_jev_trader` retorna JSON com probabilidades somando 1.
  - `pytest test_guardrails.py` — mensagem recomendação sem `call_jev_trader` é bloqueada por `before_model_callback`.
- **Integração (requer GOOGLE_API_KEY + TYPESAFE_API_KEY):**
  - `adk run jev_conversacional` + input "PETR4 swing?" → web search real + Jev real + resposta PT-BR com disclaimer.
  - `adk web` → inspecionar `Events` e `State` (`user:perfil_risco`) no Dev UI.
  - LGPD: apagar `Session` + `MemoryService` entry e `load_memory` retorna vazio.
- **E2E golden:** `adk evaluate` + `eval_conversations.py` 20 diálogos; critérios: 100% recomendação chamou `call_jev_trader`, 100% citou fontes quando grounding ocorreu, linguagem cautelosa quando `confidence<0.60`.

**Maior risco de validação:** `InMemoryMemoryService` faz keyword matching (não semântico) — recall pode falhar com paráfrase. Mitigar migrando para `VertexAiMemoryBankService` em prod; teste inclui paráfrase "minha posição em Petrobras" → deve recall "PETR4 8%".

## Risks / Rollback

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Gemini alucina recomendação sem `call_jev_trader` | Quebra auditabilidade/CVM | `before_model_callback` bloqueia em código; prompt reforça "sempre chame tool" |
| `InMemoryMemoryService` perde dados no restart | Memória some entre deploys | Dev ok; prod exige `VertexAiMemoryBankService` (persistido no Agent Engine) |
| `google_search` traz rumor | State contaminado | Ranking ADK + `informacao_insuficiente` gate → hold; sumarizador marca domínio não confiável |
| Grounding indisponível / latência | Sem notícias | Fallback Tavily/Brave `FunctionTool` + cache; modo eco reusa `temp:last_jev_state` <5 min |
| Chaves `GOOGLE_API_KEY`/`TYPESAFE_API_KEY` vazam | Abuso | `.env` + Secret Manager (Vertex), nunca logar; `user_id` hasheado nos logs Jev |
| `jev-latest` drift | Probabilidades mudam | Pinar `model` no log, golden semanal, override `jev-1.13.0` |

**Rollback:** Flags `USE_ADK_V1` + `USE_JEV_TOOL`. Se `call_jev_trader` falha, `before_tool_callback` retorna erro amigável e root_agent pede confirmação sem quebrar `Runner`. `adk web` permite rewind de `Session` para debug.

## Open Questions

- **Q1 — Session/Memory prod:** `InMemory*` (dev) já definido; confirmar migração para `VertexAiMemoryBankService` (requer GCP Project + Agent Engine) vs `VertexAiRagMemoryService` (Knowledge Engine) — custo vs semântica? Assunção: Memory Bank.
- **Q2 — Modelo Gemini:** `gemini-flash-latest` (rápido/barato) vs `gemini-pro-latest` (qualidade) para `root_agent`? Assunção: flash para v1, pro para casos `confidence<0.60`.
- **Q3 — Deploy ADK:** `adk web` (dev) validado; escolher `Cloud Run` vs `Vertex AI Agent Engine` para prod — preferência infra?
- **Q4 — Fonte cotações:** yfinance (grátis) vs Brapi/B3 pago — yfinance cobre `candles_14d`/`rsi_14` em v1? Confirmar antes da Fase 3.

## Sources

- https://adk.dev/get-started/python/ — `pip install google-adk`, `adk create my_agent` → `my_agent/agent.py` + `.env`, `root_agent = Agent(model="gemini-flash-latest", ..., tools=[...])`, `GOOGLE_API_KEY` em `.env`, `adk run` / `adk web --port 8000` (dev only)
- https://adk.dev/get-started/about/ — componentes `Tool`, `Session`/`State`, `Memory`, `Runner`, `Agent` hierárquico, `SessionService` + `MemoryService`, `load_memory` tool, `InMemory*` vs `VertexAi*`
- https://adk.dev/sessions/memory/ — `MemoryService` (`InMemoryMemoryService` keyword sem persistência; `VertexAiMemoryBankService` extrai memórias significativas via LLM e consolida; `VertexAiRagMemoryService` vector search), `add_session_to_memory` / `add_events_to_memory` / `add_memory` / `search_memory`, `load_memory` tool, `Runner` com `memory_service`, `add_session_to_memory` após sessão
- https://adk.dev/sessions/state/ — `State` scratchpad por `Session` com escopos `app:`/`user:`/`temp:`
- https://adk.dev/tools-custom/function-tools/ — `FunctionTool`, `AgentTool`, `before_model_callback`/`before_tool_callback`
- https://adk.dev/grounding/google_search_grounding/ — `Google Search Grounding` para agentes
- https://adk.dev/tutorials/agent-team/ — agent team, delegação, `Session State` para personalização, safety callbacks
- https://adk.dev/ + https://adk.dev/runtime/ — estrutura ADK, `Runner`, `adk web`/`adk run`, modelos (`gemini-flash-latest`, `gemma`, `claude`, etc.)
- https://docs.typesafe.ai/introduction/quickstart — `POST /v1/systemone`, `model: jev-latest`, `Choice`/`Score`/`Noul`, `probabilities`/`confidence`/`noul`
- https://docs.typesafe.ai/concepts/state.md — State objeto nomeado, texto apenas, inglês primário
- https://docs.typesafe.ai/primitives.md — `type`/`instructions`/`criteria`, 1 julgamento atômico, `confidence=(n*peak-1)/(n-1)`, fan-out
- `docs/plans/2026-09-20-jev-trader.md` — contrato Jev-Trader herdado (6 chaves, 9 perguntas, composer)
- `docs/plans/2026-09-20-jev-conversacional.md` — spec conversacional anterior (base para migração ADK)

---
*Spec revisada para Google ADK após inspeção direta de https://adk.dev em 2026-09-20. Aguardar aprovação para implementação.*
