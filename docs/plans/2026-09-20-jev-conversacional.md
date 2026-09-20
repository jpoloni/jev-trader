# Jev Conversacional — Spec do Agente Chat com Memória Persistente, Web Search e Jev-Trader como Subagente

## Goal
Construir o **Jev Conversacional**: agente de chat em PT-BR que mantém **memória persistente** por usuário, faz **web search** em tempo real e usa o **Jev-Trader (System One)** como subagente especialista para recomendar `compra/venda/hold`. Jev-Trader decide com probabilidades calibradas; o conversacional orquestra, explica e lembra. Código permanece no controle — o LLM conversacional (System 2) nunca substitui os julgamentos tipados do Jev.

## Success Criteria
- [ ] Usuário consegue conversar em linguagem natural ("vale comprar PETR4?", "e se eu aumentar para 15% da carteira?") e recebe resposta com recomendação tipada + justificativa + disclaimer CVM.
- [ ] Memória persiste entre sessões: após `User: sou moderado, horizonte swing, tenho PETR4 8%` e nova sessão dias depois, o agente recupera perfil e posição sem re-perguntar.
- [ ] Web search automático: ao pedir recomendação, o agente busca cotação, notícias 7d e eventos próximos e injeta em `State.contexto` antes de chamar o subagente — sem exigir que usuário cole dados.
- [ ] Chamada ao Jev-Trader é sempre 1 `POST /v1/systemone` com `model: jev-latest` e 9 perguntas paralelas (fan-out), via SDK `typesafe-sdk`; resposta do subagente é auditável (model, probabilities, confidence, usage).
- [ ] Gating de confiança respeitado no chat: `confidence <0.60` ou `noul(risco_excessivo)>0.70` vira `hold` com linguagem cautelosa + oferta de escalonamento humano, nunca `compra/venda` assertiva.
- [ ] Histórico de 20 conversas de teste com recall de memória >85% e web search com fontes citadas.

## Context And Current Facts

**Herança — Jev-Trader (spec aprovada 2026-09-20, `docs/plans/2026-09-20-jev-trader.md`):**
- State objeto canônico com 6 chaves: `ativo`, `mercado` (candles_14d + indicadores RSI/MACD/MM calculados em código), `fundamentos`, `contexto` (noticias_7d, eventos_proximos, sentimento_mercado), `posicao_usuario`, `restricoes` (disclaimer).
- 9 perguntas em 1 chamada: 5 `Score` (tendencia_tecnica, qualidade_fundamentalista, risco_volatilidade, sentimento_noticia, timing_momentum) + 3 `Noul` (risco_excessivo, informacao_insuficiente, evento_binario_iminente) + 1 `Choice` (recomendacao compra/venda/hold). Instructions em inglês com backticks `` `campo.path` ``, criteria ordenado (Score) ou categórico (Choice).
- Composer em código com pesos versionados (`weights.yaml`), thresholds `weighted>=0.62 compra / <=0.38 venda` e gates soberanos Noul + `confidence<0.60 => hold`. Pesos e thresholds são auditáveis.
- Princípios Typesafe validados: System One = julgamentos rápidos tipados (não chat), State texto apenas, `Choice` retorna `choice+probabilities+confidence`, `Score` retorna `score+legend+probabilities+confidence`, `Noul` retorna `noul` 0..1, todos veem mesmo State em paralelo, `confidence = (n*peak-1)/(n-1)`, padrões Speculative Fan-out, Confidence-gated Routing e Composite Scoring.

**Workspace:**
- Greenfield `/Users/jpoloni/dev/jev`, sem DB ou framework prévio; primeira spec (Jev-Trader) ainda não implementada — esta spec deve reutilizar seu contrato sem duplicar lógica.

**Necessidade conversacional:**
- Jev não gera texto livre nem mantém memória — é System One. Para chat é preciso um LLM System Two (ex.: GPT-4o / Claude / Gemini) como orquestrador que: interpreta intenção, gerencia memória, decide quando buscar web e quando chamar o subagente, e traduz a saída tipada em explicação humana.
- Memória persistente e web search não são nativos da Typesafe; ficam no código do orquestrador e alimentam o State do Jev-Trader.

## Constraints And Non-goals

**Constraints:**
- Separação System One / System Two rígida: LLM conversacional não "chuta" recomendação; sempre que `intent == recomendacao_acao` e ticker identificado, delega ao Jev-Trader. Resposta sem subagente é proibida para recomendação.
- LGPD + CVM: memória é opt-in, apagável sob pedido, sem PII em logs do Jev; toda mensagem com recomendação carrega disclaimer educacional e não executa ordem.
- Custo/latência: 1 chamada Typesafe por recomendação (fan-out já barato); web search com cache 15 min por ticker; memória com retrieval top-k limitado (8) para não estourar contexto.
- Idioma: chat em PT-BR para usuário, mas `instructions` do Jev-Trader permanecem em inglês (maior acurácia documentada) — orquestrador traduz na borda.
- State continua texto apenas; gráficos/candles viram JSON textual.

**Non-goals (v1):**
- Execução de ordens na corretora, multi-ativo com rebalanceamento automático, fine-tuning de Jev, voz/áudio, app mobile nativo (só API + webchat primeiro).

## Key Decisions

| # | Decisão | Recomendação | Alternativa rejeitada | Por quê |
|---|---------|--------------|----------------------|---------|
| 1 | **Arquitetura orquestrador vs monolito** | Orquestrador System Two (LLM chat) + Jev-Trader como **tool/subagente** `call_jev_trader` | LLM único faz tudo (prompt "analise e recomende") | Violação do princípio "code in control" e "one snap judgment per question"; monolito esconde pesos, não retorna probabilidades calibradas nem confidence gating. Subagente preserva auditabilidade Typesafe. |
| 2 | **Framework de orquestração** | **Código puro + function calling** (OpenAI/Anthropic tool use) sem framework pesado; LangGraph como opcional futuro | CrewAI / AutoGen multi-agente | Para v1, 1 orquestrador + 1 subagente não justifica framework multi-agente; function calling nativo é mais simples, testável e portável. |
| 3 | **Memória persistente** | **SQLite + pgvector (ou Chroma para v1 local)** com 3 camadas: `profile` (fatos extraídos), `episodic` (resumo de sessão), `decision_history`. Retrieval híbrido (BM25 + vector top-8). Escrita via summarizer pós-turno. | Só janela de contexto ou só vector store sem curadoria | Janela perde entre sessões; vector puro acumula ruído e contradições. Camadas + consolidação permitem `pct_carteira`, `perfil_risco` estáveis e esquecimento seletivo. |
| 4 | **Web search** | **Tavily API** (ou Brave Search como fallback) + `fetch_url` + sumarizador LLM; cache Redis/内存 15 min por ticker; fontes preferidas (Reuters, Valor, RI) | Scraper genérico sem ranking ou sem cache | Tavily/Brave retornam ranking + recency + snippet pronto para LLM; cache evita custo e respeita rate limit; sumarizador reduz contexto para State. Assunção marcada como configurável. |
| 5 | **Quando buscar web vs memória** | Política: se `intent == recomendacao_acao` e ticker presente, **sempre** web search (cotação + noticias_7d + eventos) + memory recall em paralelo; se pergunta é follow-up ("por que hold?"), reusar último State cacheado | Buscar só se usuário pedir | Recomendação desatualizada é pior que custo extra; fan-out paralelo torna busca quase grátis em latência. |
| 6 | **Intent routing** | Orquestrador LLM classifica intent via function calling; **opcional** validar com Jev `Choice` intent em futuro (Intent Routing pattern) | Regex de palavras-chave | LLM entende variações PT-BR ("vale a pena entrar em PETR4?" = compra); regex é frágil. Jev Choice para intent fica como evolução quando volume justificar. |
| 7 | **Tradução de saída tipada para chat** | Template em código + LLM parafraseia: orquestrador recebe `composer_output` JSON e gera PT-BR com seções `Recomendação`, `Confiança`, `Por quê (scores)`, `Riscos/Gates`, `Disclaimer` e cita fontes web | LLM reescreve livremente sem template | Template garante disclaimer e números (probabilities/confidence) nunca omitidos; LLM apenas humaniza. |
| 8 | **Persistência de conversa** | `conversations` (turnos brutos) + `memories` (fatos curados) separados; `user_id` como chave; TTL opcional para episodic | Tudo em um log único | Separação permite retrieval seletivo (só profile para State) e deleção LGPD por tipo. |

## Recommended Approach

### 1. Arquitetura

```
[User] --(PT-BR)--> [Jev Conversacional — LLM System Two]
                         |-> [Memory Service] --recall--> <memory> injetada no prompt
                         |-> [Web Search Service] --query--> Tavily/Brave --summarize--> noticias_7d/eventos
                         |-> [Intent -> tool call?] --se recomendacao_acao--> [Jev-Trader Subagente]
                                                                  |-> [Normalizer + Indicadores] (código)
                                                                  |-> State canônico (objeto, 6 chaves)
                                                                  |-> POST /v1/systemone (9 perguntas, jev-latest)
                                                                  |-> Composer (pesos+ gates) -> {recomendacao, confidence, probabilities, scores, gates, justificativa}
                         |-> [Explainer] template + LLM paraphrase + disclaimer + citações
                         |-> [Memory Writer] summarizer -> upsert memories
                         \-> Resposta PT-BR + persistência
```

**Capas de LLM:**
- **Orquestrador:** System Two para diálogo, com system prompt que define papel, memória, tools e regra "nunca recomende sem call_jev_trader".
- **Summarizers:** mesmo LLM com prompt focado (extração de fatos, sumarização web).

### 2. Memory Service — spec

**Schema `memories`:**
```sql
memories(id, user_id, kind ENUM('profile','portfolio','preference','episodic_summary','decision'), content TEXT, embedding VECTOR(1536), source_turn_id, created_at, updated_at, superseded_by)
conversations(id, user_id, role, content, tool_calls JSON, created_at)
```

**Kinds:**
- `profile`: "perfil_risco=moderado, horizonte=swing 2-8 semanas"
- `portfolio`: "tem PETR4 8% carteira, preço médio 35.00"
- `preference`: "prefere não operar small caps"
- `episodic_summary`: resumo de sessão "2026-09-19: discutiu PETR4, recomendação hold por evento Copom"
- `decision`: "2026-09-20T14:03 PETR4 hold (confidence 0.62, weighted 0.51)"

**Ciclo:**
1. **Recall (read):** no início do turno, embedding da mensagem do usuário + `SELECT ... ORDER BY hybrid_score LIMIT 8` + filtro `superseded_by IS NULL`. Injeta como:
   ```
   <memoria>
   - [profile] perfil moderado, swing
   - [portfolio] PETR4 8% @35.00 (2026-09-19)
   - [decision] último PETR4: hold 2026-09-20 (conf 0.62)
   </memoria>
   ```
2. **Write (pós-resposta):** summarizer LLM extrai fatos novos do turno com prompt:
   ```
   Extraia apenas fatos novos e duráveis sobre o usuário. Retorne JSON {facts:[{kind, content}]}. Ignore saudações.
   ```
   Upsert com deduplicação (se `profile` contradiz anterior, marca `superseded_by`).

**LGPD:** endpoint `DELETE /users/{id}/memories` apaga embeddings e conversas; logs do Jev não contêm `user_id` em claro (hash).

### 3. Web Search Service — spec

**Tools do orquestrador:**
```json
{
  "web_search": {"query": "PETR4 cotação hoje", "time_range": "7d", "top_k": 8},
  "fetch_url": {"url": "https://api.mz.../petr4-ri"}
}
```

**Geração de queries (código, não LLM livre):**
- `f"{ticker} cotação {hoje}"` , `f"{ticker} notícias últimos 7 dias"` , `f"{ticker} balanço resultados"` , `f"Ibovespa hoje"`
- Fallback yfinance/B3 API para `mercado.preco_atual` e candles (fonte determinística, não LLM).

**Pipeline:**
```
web_search x3 em paralelo -> rank (recency + domínio confiável) -> fetch top 3 -> LLM sumariza em 3-5 bullets PT-BR -> injeta em State.contexto.noticias_7d
cotação API -> mercado.preco_atual, variacao_dia_pct, candles_14d
```

**Cache:** chave `web:{ticker}:{data}` TTL 15 min (Redis ou dict em memória v1).

**Citações:** guardar `sources: [{titulo, url, data}]` para exibir no chat: "Fontes: Reuters 19/09, Valor 18/09".

### 4. Jev-Trader como Subagente — contrato

**Tool definition (function calling):**
```json
{
  "name": "call_jev_trader",
  "description": "Chama o especialista Jev-Trader para recomendação compra/venda/hold. Use quando usuário pede recomendação de ação para um ticker.",
  "parameters": {
    "type": "object",
    "required": ["ticker"],
    "properties": {
      "ticker": {"type": "string", "description": "Código B3, ex.: PETR4"},
      "horizonte_override": {"type": "string", "enum": ["daytrade","swing","posicional"]},
      "observacao_usuario": {"type": "string"}
    }
  }
}
```

**Handler `call_jev_trader` (código, não LLM):**
1. Recall memória -> `posicao_usuario` (pct_carteira, preco_medio, perfil_risco, horizonte)
2. Web search + yfinance -> `mercado` + `contexto` + `fundamentos` (parcial, se não houver web, marca `informacao_insuficiente`)
3. Monta State canônico (reusa `jev_trader/state.py` da spec anterior)
4. Chama `jev_trader/questions.py` (9 perguntas) via `TypeSafeClient().system_one(state, questions, model="jev-latest")`
5. Roda `jev_trader/composer.py` -> `composer_output`
6. Retorna JSON tipado ao orquestrador (não texto livre):
```json
{
  "ticker":"PETR4","recomendacao":"hold","confidence":0.62,
  "probabilidades":{"compra":0.28,"venda":0.11,"hold":0.61},
  "scores":{"tendencia_tecnica":3.4,"qualidade_fundamentalista":3.0},
  "gates":{"risco_excessivo":0.41,"evento_binario_iminente":0.72},
  "justificativa":"Tendência neutra-alta mas evento Copom em 2 dias (gate) + RSI 68 sobrecompra",
  "model":"jev-1.13.0","usage":{"input_tokens":842,"output_tokens":78},
  "sources":[...]
}
```

**Regra de ouro:** orquestrador nunca inventa `recomendacao`; se tool não foi chamada, resposta deve ser pergunta de esclarecimento ("qual ticker e horizonte?").

### 5. Fluxo de Conversa — exemplos

**Caso A — Recomendação nova:**
```
User: "Vale comprar PETR4 pra swing?"
-> recall: perfil moderado, tem 8% PETR4
-> web_search PETR4 (cotação 38.42, RSI 68, notícias reajuste diesel, Brent +1.5%, Copom 20/09)
-> call_jev_trader(ticker=PETR4)
<- {recomendacao: hold, confidence 0.62, gates: evento_binario_iminente 0.72}
-> explainer PT-BR:
   "Recomendação: **HOLD** (manter/aguardar) — confiança 0.62 (moderada).
    Por quê: tendência levemente de alta, fundamentos sólidos, mas Copom em 2 dias deixa direção incerta (gate) e RSI 68 indica sobrecompra.
    Probabilidades Jev: hold 61%, compra 28%, venda 11%.
    Fontes: Reuters 19/09, Valor 18/09.
    ⚠️ Conteúdo educacional, não é recomendação personalizada (CVM). Quer que eu te avise após o Copom?"
-> memory_writer: decision PETR4 hold 2026-09-20
```

**Caso B — Follow-up com memória:**
```
User: "E se eu aumentar para 15% da carteira?"
-> recall: tem 8% @35, quer 15%
-> call_jev_trader com posicao_usuario.pct_carteira=15 (simulação)
<- {risco_excessivo 0.78 => hold}
-> "Com 15% o risco sobe (gate risco_excessivo 0.78) — mesmo com tendência boa, eu manteria hold. Quer simular venda parcial?"
```

### 6. Prompt do Orquestrador (trecho)

```
Você é o Jev Conversacional, assessor educacional em PT-BR.
- Use <memoria> para personalizar, mas nunca revele IDs internos.
- Para qualquer pedido de compra/venda/hold com ticker, CHAME call_jev_trader. Nunca responda sem chamar.
- Após receber o JSON do Jev-Trader, explique em PT-BR com: Recomendação, Confiança, Por quê, Riscos/Gates, Fontes e Disclaimer CVM fixo.
- Se confidence <0.60 ou gate >0.70, use linguagem cautelosa e ofereça acompanhamento.
- Cite fontes web com título + data.
```

### 7. Observabilidade
- Log por turno: `user_id_hash`, `intent`, `tool_calls`, `jev_model`, `jev_confidence`, `web_queries`, `latência`, `tokens` (LLM + Jev `usage`).
- Dashboard: taxa `hold` por baixa confiança, recall memória, hit rate cache web, distribuição `recomendacao`.

## Work Plan

| Fase | Entregável | Detalhe | Dep |
|------|-----------|---------|-----|
| **1 — Jev-Trader base** | Reuso `docs/plans/2026-09-20-jev-trader.md` | Implementar `jev_trader/state.py`, `questions.py`, `composer.py`, `weights.yaml` e testes unitários (ou mock se ainda não implementado). | — |
| **2 — Memory Service** | `conversational/memory/` | SQLite + pgvector/Chroma, schema acima, `recall()` híbrido e `extract_and_upsert()` com LLM summarizer; `pytest test_memory_recall` com 5 conversas simuladas. | 1 |
| **3 — Web Search Service** | `conversational/web/` | Wrapper Tavily/Brave + yfinance, `search_and_summarize(ticker)`, cache 15 min, ranking por recency/domínio; testes com respostas mockadas. | 1 |
| **4 — Subagente Tool** | `conversational/tools/call_jev_trader.py` | Handler que monta State (memória+web), chama Typesafe, roda composer e retorna JSON tipado; valida que `response.answers` tem 9 chaves. | 2,3 |
| **5 — Orquestrador Chat** | `conversational/orchestrator.py` + `prompts/` | LLM System Two com function calling, system prompt PT-BR, loop `recall -> intent -> (web+tool) -> explainer`; CLI `chat --user-id u123`. | 4 |
| **6 — API + Frontend** | `app_chat.py` (FastAPI) + `webchat/` | `POST /chat {user_id, message}` com SSE/stream, `GET /users/{id}/memories`, `DELETE /users/{id}/memories`; webchat simples. | 5 |
| **7 — Eval & Docs** | `fixtures/conversations/` + `docs/jev-conversacional.md` | 20 diálogos golden (inclui 5 com memória cross-sessão, 5 com follow-up "e se eu..."), métrica recall memória e citação de fontes; README com curl e Playground Jev. | 6 |

Fases 1-2 podem rodar em paralelo; 3 depende de 1.

## Validation Plan

- **Unitário:**
  - `pytest conversational/test_memory.py` — após 3 turnos, `recall("PETR4")` retorna `portfolio` correto; atualização de perfil marca `superseded_by`.
  - `pytest conversational/test_web.py` — com mock Tavily, `search_and_summarize("PETR4")` retorna `noticias_7d` com 3 bullets e `sources` com URLs; cache hit não chama API.
  - `pytest conversational/test_call_jev_trader.py` — mock `TypeSafeClient.system_one` retorna `choice: hold, confidence 0.62`; handler retorna JSON com `recomendacao` e `probabilidades` somando 1.
  - `pytest conversational/test_orchestrator.py` — mensagem "vale comprar PETR4?" dispara `call_jev_trader`; mensagem "oi" não dispara.
- **Integração (requer TYPESAFE_API_KEY + TAVILY_API_KEY):**
  - `python -m conversational.orchestrator --user-id test --message "PETR4 swing?"` faz web search real, chama Jev real e retorna PT-BR com disclaimer.
  - Teste LGPD: `DELETE /users/test/memories` + `recall` retorna vazio.
- **Playground (manual):**
  - Colar State gerado pelo orquestrador no Playground Typesafe e comparar `Choice.recomendacao` vs `composer_output.final` — devem coincidir quando gates não atuam.
- **E2E golden conversations:**
  - `scripts/eval_conversations.py` roda 20 diálogos (inclui "comprei PETR4 ontem a 35, devo vender?" com memória) e verifica: 100% dos casos de recomendação chamaram subagente, 100% citaram fontes quando web search ocorreu, linguagem cautelosa quando `confidence<0.60`.

**Maior risco de validação:** Memória injeta fatos contraditórios (ex.: perfil agressivo antigo vs moderado novo). Mitigar com `superseded_by` e teste de contradição que prioriza fato mais recente.

## Risks / Rollback

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| LLM conversacional alucina recomendação sem chamar Jev | Quebra auditabilidade + risco CVM | Guardrail em código: se `intent==recomendacao` e `tool_calls` não contém `call_jev_trader`, bloquear resposta e retornar erro interno |
| Memória drift (ex.: carteira desatualizada) | Recomendação com `pct_carteira` errado | Sempre confirmar `pct_carteira` no State com dado mais recente; oferecer "atualizar carteira?" a cada 7 dias |
| Web search traz rumor/fake | State contaminado | Ranking por domínio confiável + recency, sumarizador marca "fonte não verificada" se domínio desconhecido; gate `informacao_insuficiente` força hold |
| Custo LLM + Jev + Tavily escala | Latência/custo | Cache web 15 min, memória top-8, Jev 1 chamada; modo `eco` que reusa último State se <5 min |
| Vazamento de chave (TYPESAFE/TAVILY/LLM) | Abuso | Secrets via env, nunca logar; hash de user_id nos logs Jev |
| Dependência jev-latest drift | Probabilidades mudam | Pinar `model` em log, teste golden semanal, fallback `jev-1.13.0` pinável |

**Rollback:** Feature flags `USE_CONVERSATIONAL_V1` e `USE_JEV_SUBAGENT`. Se subagente falhar, orquestrador cai para modo "explicação sem recomendação" (coleta dados e pede confirmação) sem quebrar chat.

## Open Questions

- **Q1 — Provedor LLM System Two:** GPT-4o vs Claude Sonnet vs Gemini para orquestrador? Assunção: OpenAI GPT-4o com function calling para v1 (melhor suporte PT-BR + tool use estável). Confirmar custo/latência e preferência do time.
- **Q2 — Vetor DB em produção:** pgvector (Postgres) vs Chroma local vs Qdrant cloud? Assunção v1: Chroma local para dev, pgvector em prod para unificar com transações. Validar com infra.
- **Q3 — Canais:** Webchat primeiro ou já WhatsApp/Telegram? Assunção: API + webchat simples em v1, WhatsApp via provider (Twilio) em v2. Confirmar prioridade.
- **Q4 — Fonte determinística de cotação/candles:** yfinance gratuito vs B3 oficial vs provedor pago (Profit, Brapi)? Assunção yfinance + cache, mas Brapi pode ser mais estável para B3. Decidir antes da Fase 3.

## Sources

- https://docs.typesafe.ai/introduction/quickstart — endpoint `POST /v1/systemone`, `model: jev-latest`, body `state`+`questions`, `Choice`/`Score`/`Noul`, `response.answers` com `probabilities`/`confidence`/`noul`/`legend`, SDK `TypeSafeClient`
- https://docs.typesafe.ai/concepts/state.md — State string/objeto/array, objeto nomeado preferido, todos questions veem mesmo state, texto apenas, inglês primário
- https://docs.typesafe.ai/concepts/system-one.md — System One = julgamentos rápidos tipados com probabilidades calibradas, não gera texto livre, diferença LLM vs System One
- https://docs.typesafe.ai/primitives.md — `type`/`instructions`/`criteria`/`id`, 1 julgamento atômico por pergunta, escolher tipo pelo formato da resposta, `probabilities`+`confidence`, independência/paralelismo, speculative fan-out e composite scoring, paths com backticks
- https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md — código no controle, decompor julgamentos, combinar em código
- https://docs.typesafe.ai/patterns.md — catálogo de padrões
- https://docs.typesafe.ai/patterns/composite-scoring.md — quebrar julgamento complexo em scores atômicos + pesos em código
- https://docs.typesafe.ai/patterns/confidence-routing.md — confidence como segundo eixo (o que vs se deve agir), escalar para humano
- https://docs.typesafe.ai/confidence.md — `confidence = (n*peak-1)/(n-1)`, uso para gating
- https://docs.typesafe.ai/patterns/fan-out.md — speculative fan-out: muitas perguntas em 1 chamada, custo só tokens, latência quase constante
- `docs/plans/2026-09-20-jev-trader.md` (repo local) — contrato Jev-Trader herdado (State 6 chaves, 9 perguntas, composer com pesos e gates)

---
*Spec gerada após inspeção direta da doc Typesafe em 2026-09-20. Aguardar aprovação para implementação.*
