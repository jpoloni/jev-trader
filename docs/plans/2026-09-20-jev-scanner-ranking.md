# Jev Scanner — Varredura B3 Completa e Ranking (Typesafe jev-latest × ADK)

## Goal
Permitir que o Jev, com custo muito baixo por call, varra **toda a lista oficial B3** (~800 tickers de ações/units) e devolva um **ranking ordenado das melhores oportunidades** (compra > hold > venda) para um horizonte/perfil dados, reaproveitando o motor já validado `State 6 chaves + 9 perguntas fan-out + composer weighted + gates`. A rotina deve rodar off-line (cron diário) e on-demand via ADK (`scan_b3`), sem quebrar as 13 unit + 10 e2e já verdes.

## Success Criteria
- [ ] `python -m jev_trader.scanner --universe b3 --horizonte swing --top 20 --mock` retorna em <30s um `ranking.json` determinístico, ordenado por `recomendacao → weighted → confidence`, com `disclaimer` em todos os itens, sem chamar Typesafe real.
- [ ] `python -m jev_trader.scanner --universe b3 --live` com `TYPESAFE_API_KEY` real produz `ranking-live.json` com `model startswith jev-`, `probabilidades` somando 1, `motivo_gate` quando aplicável, e custo logado (`usage.input_tokens`).
- [ ] Pré-filtro de liquidez reduz universo ~800 → ~200-300 antes do Typesafe (validado por `volume_medio_20d` via yfinance ou mock), sem remover manualmente tickers líderes (PETR4, VALE3, ITUB4 sempre passam).
- [ ] Top N (20) é re-enriquecido com `google_search` + `get_market_data` completo em 2ª fase; ranking final inclui `Fontes:` quando enriquecido.
- [ ] Ferramenta ADK `scan_b3(tickers?, top?, horizonte?)` exposta no `root_agent` responde em PT-BR: **Recomendação / Por quê / Riscos / Fontes / Disclaimer** + lista ordenada, usando `ranking.json` em cache (<15 min) sem re-varrer.
- [ ] `pytest -q` continua verde; novos testes `tests/test_scanner_*.py` cobrem ordenação, gates, e fallback sem rede.

## Context And Current Facts

**Onde estamos (verificado 2026-09-20 no workspace):**
- `jev_trader/state.py`: `build_state` com 6 chaves (`ativo`, `mercado`, `fundamentos`, `contexto`, `posicao_usuario`, `restricoes`), candles 14d + indicadores calculados em código, `validate_state`.
- `jev_trader/questions.py`: 9 perguntas em 1 chamada — 5 `Score` (tendencia, fundamentos, risco_volatilidade, sentimento, timing), 3 `Noul` (risco_excessivo, informacao_insuficiente, evento_binario_iminente), 1 `Choice` (compra/venda/hold) com instructions em inglês e backticks.
- `jev_trader/composer.py` + `weights.yaml`: `weighted = 0.30*tend + 0.25*fund + 0.15*sent + 0.15*timing_inv + 0.15*risco_inv`, thresholds `compra >=0.62 / venda <=0.38`, gates `risco_excessivo 0.70, evento_binario 0.65, info_insuf 0.68, confidence_min 0.60` → `hold` soberano.
- `jev_trader/client.py`: `call_jev_trader(ticker, state_override, mock_answers)` — 1 chamada `TypeSafeClient.system_one(state, QUESTIONS, model="jev-latest")`, fallback mock `jev-mock` quando sem `TYPESAFE_API_KEY`.
- `jev_conversacional/agent.py`: `LlmAgent(model=gemini-3.8-flash, tools=[load_memory, google_search, get_market_data, call_jev_trader])`, `generate_content_config.tool_config.include_server_side_tool_invocations=True` já validado (`adk run "oi"` OK).
- `jev_conversacional/tools/market_data.py`: `get_market_data` com cache 15min, yfinance + fallback mock, calcula `rsi_14`, `volatilidade_20d_pct`.
- Universo B3: Wikipedia registra 475 empresas listadas em 10/2022; B3 estudo 2026 analisou 290 companhias ativas; Ibovespa são 87 ativos; tickers de ações/units ~700-900 (4 letras + número) + BDRs/ETFs/FIIs elevam listagens >2000. Jev valida ticker via `re.match(r"^[A-Z]{4}\d{1,2}(\.SA)?$")` em `before_tool_callback`.
- Fonte oficial B3: página `https://www.b3.com.br/en_us/products-and-services/trading/equities/listed-companies.htm` e API não-oficial mas pública `https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/` usada por projetos `brasa`, `b3-market-data`; endpoint de lista é paginado e sem auth, mas sem SLA — precisa fallback.
- Typesafe: `POST https://api.typesafe.ai/v1/systemone`, `model: jev-latest`, response `{model:"jev-1.13.0", answers:{id:{score/noul/choice, probabilities, confidence, legend}}, usage:{input_tokens, output_tokens}}`; todos `questions` veem mesmo `state` em paralelo; custo é por tokens de `state` + `questions` (poucos cents/call).

**Custo observado:** usuário relata custo muito baixo; 250 calls/dia ≈ < $1/dia no modelo jev-latest (tokens de state ~1.5k), viabiliza varredura diária.

## Constraints And Non-goals

**Constraints:**
- Não quebrar contrato Typesafe: 1 chamada por ticker com as mesmas 9 perguntas; pesos e gates continuam em `composer.py`/`weights.yaml` versionados.
- Não chamar `google_search` para os ~250 tickers na 1ª fase (quota/latência); só para Top N na 2ª fase.
- `TYPESAFE_API_KEY` nunca em log/snapshot; modo `--mock` deve funcionar offline e em CI sem chaves.
- `yfinance` é best-effort (delay 15min, fora do ar em feriado); scanner precisa fallback mock e não falhar por 1 ticker.
- Respeitar rate limit Typesafe (não documentado como hard, mas tratar 429 com backoff exponencial); concorrência limitada por `semaphore`.
- Saída sempre com disclaimer CVM e sem executar ordem.

**Non-goals (v1):**
- Otimização de carteira (Markowitz, alocação % por ticker), backtest histórico, execução de ordens, `VertexAiMemoryBankService`, análise de FIIs/BDRs/ETFs (só ações/units).

## Key Decisions

| # | Decisão | Recomendação | Alternativa rejeitada | Por quê |
|---|---------|--------------|----------------------|---------|
| 1 | **Fonte do universo** | Primária: `sistemaswebb3-listados.b3.com.br/listedCompaniesProxy` + parser `CompanyCall/GetListedCash`, fallback: `data/universe.json` com snapshot Ibovespa 87 + lista curada ~250 líquidos | Só lista hard-coded Ibovespa | B3 oficial é completa (~800), mas é API não contratada e pode mudar; fallback garante offline/CI verde. Brasa e b3-market-data já provam endpoint estável sem auth. |
| 2 | **Pré-filtro antes do Typesafe** | Filtro de liquidez em código: `get_market_data` → `preco>2` e `volume_medio_20d` ou `volatilidade` dentro de banda; remove penny/ilíquidos; PETR4/VALE3/ITUB4 sempre passam via allowlist | Varrer 800 puros no Typesafe | Corta 60-70% de calls sem perder alfa (ilíquidos raramente são top compra); economia direta de custo e tempo (800→250). |
| 3 | **Concorrência** | `asyncio` + `Semaphore(6-8)` + `httpx`/`typesafe_sdk` async, retry 429 com backoff 1s/2s/4s + jitter, `asyncio.gather` com `return_exceptions=True` | Sequencial ou `ThreadPool` sem limite | Typesafe já avalia perguntas em paralelo por ticker; paralelizar tickers com limite evita 429 e mantém latência ~3-4min para 250. Sync sequencial levaria >20min. |
| 4 | **State no scan (fase 1)** | State leve: `candles_14d` + `indicadores` (yfinance) + `posicao_usuario` do horizonte solicitado; `noticias_7d = ["(varredura sem google_search)"]`, `fundamentos = {observacao:"varredura"}` | State completo com google_search por ticker | google_search para 250 tickers estoura quota/latência e não muda ordem do ranking grosso; refinamento só no Top 20. |
| 5 | **Ranking** | Determinístico em `composer.py`: chave `(-is_compra, -weighted, -confidence, ticker)`; `hold` por gate rebaixa mas mantém ordem por `weighted`; desempate por ticker | Pedir ao Gemini para ordenar | Código é auditável, reproduzível e não custa LLM; ordenação por `weighted` reflete `weights.yaml` versionado. |
| 6 | **Duas fases** | Fase 1: scan leve → ranking bruto; Fase 2: `enrich_top_n(top=20)` com `google_search` + `get_market_data` completo + re-call Typesafe só nesses | Uma fase só com tudo | 2 fases mantém custo baixo e ainda entrega Fontes e sentimento real onde importa (top compras). |
| 7 | **Persistência** | `data/ranking-YYYY-MM-DD.json` + `data/ranking-latest.json` + `ranking.csv` (ticker, recomendacao, weighted, confidence, motivo_gate, model, timestamp); rotação mantém 30 dias | Só em memória | Permite ADK ler cache sem re-varrer, auditoria e `adk web` mostrar histórico; CSV facilita Excel/Sheets. |
| 8 | **Agendamento** | Cron `0 18:30 America/Sao_Paulo * * 1-5` (após fechamento) via `cron` ou `systemd timer`; on-demand `python -m jev_trader.scanner` e tool ADK `scan_b3` | Só on-demand | Varredura diária após fechamento captura candles do dia; on-demand cobre pedido do usuário "quero agora". |
| 9 | **ADK integration** | Nova `FunctionTool scan_b3(horizonte, top, universe, force_refresh)` que lê `ranking-latest.json` se fresco (<15min) ou dispara `scanner` em background e retorna lista formatada PT-BR | LLM varrer tickers um a um via `call_jev_trader` | Evita N calls sequenciais do LLM (lento/caro); tool lê ranking já computado. |

## Recommended Approach

### Arquitetura
```
[B3 API / universe.json] → UniverseLoader (800) 
  → MarketDataPrefilter (yfinance cache 15min) → ~250 líquidos
  → Scanner (Semaphore 8, 1 call jev-latest/ticker, 9 perguntas) → results brutos
  → Composer (weights.yaml + gates) → ranking bruto
  → Enricher (Top 20: google_search + re-call Typesafe) → ranking final
  → Persist (JSON + CSV) → ADK scan_b3 (leitura cache)
```

### Módulos e interfaces

**1. `jev_trader/universe.py`**
```python
def load_universe(source="b3", cache_path="data/universe.json") -> list[str]:
    # tenta B3: GET https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedCash
    # parse tickers, filtra r"^[A-Z]{4}\d{1,2}$", upper, dedup, sort
    # fallback: read cache_path ou ibov 87
    # retorna ["PETR4","VALE3",...]
```

**2. `jev_trader/scanner.py`**
```python
@dataclass
class ScanResult: ticker, recomendacao, weighted, confidence, probabilidades, scores, gates, motivo_gate, justificativa, model, usage

async def scan_one(ticker, horizonte, sem) -> ScanResult
async def scan_all(tickers, horizonte="swing", concurrency=8, enrich_top=20, use_mock=False) -> list[ScanResult]
def rank(results) -> list[ScanResult]  # ordenação determinística
def persist(results, out_dir="data")   # JSON + CSV
# CLI: python -m jev_trader.scanner --universe b3 --horizonte swing --top 20 --concurrency 8 [--mock|--live] [--enrich]
```

State por ticker (fase 1):
```python
state = build_state(
  ticker=ticker,
  preco_atual=md["preco_atual"],
  candles_14d=md["candles_14d"],
  indicadores=md["indicadores"],
  noticias_7d=["(varredura sem google_search)"],
  posicao_usuario={"horizonte": horizonte, "perfil_risco":"moderado", "tem_posicao":False},
)
```

Fase 2 (enrich):
```python
for r in ranking[:enrich_top]:
  noticias = google_search(f"{r.ticker} B3 notícias últimos 7 dias")  # via ADK ou direct
  state2 = build_state(..., noticias_7d=noticias, fundamentos=...)
  r2 = call_jev_trader(ticker=r.ticker, state_override=state2)
  # substitui ranking[i] se confidence maior
```

**3. `jev_conversacional/tools/scan_b3_tool.py`**
```python
def scan_b3(horizonte: str="swing", top: int=10, force_refresh: bool=False) -> dict:
    """Ferramenta ADK: lê ranking-latest.json se fresco, senão avisa para rodar scanner.
    Retorna {ranking: [{ticker,recomendacao,weighted,confidence,fontes}], disclaimer, gerado_em}
    """
```

Registro no `agent.py` + regra dura de orquestração:
```python
from jev_conversacional.tools.scan_b3_tool import scan_b3
tools=[load_memory, google_search, get_market_data, call_jev_trader, scan_b3]
```
Instruction — acrescentar regra 7 ao bloco existente (regras 1-6 já validadas):
```
7) Para qualquer pedido de VARREDURA/RANKING ("quais as melhores ações?", "top 10 para swing",
"varre a B3", "oportunidades hoje"), CHAME SEMPRE a tool scan_b3 com {horizonte, top}.
NUNCA varra tickers um a um com call_jev_trader em loop, NUNCA invente ranking sem chamar scan_b3,
NUNCA ordene manualmente. Se scan_b3 retornar cache com >15min, avise "ranking de HH:MM" e ofereça
force_refresh. Responda sempre com lista numerada + weighted/confidence + motivo_gate + disclaimer CVM.
```
Teste durável: `assert "scan_b3" in [t.name for t in root_agent.tools]` e `assert "CHAME SEMPRE a tool scan_b3" in root_agent.instruction`.

### CLI e agendamento
```bash
# varredura mock (CI/offline)
python -m jev_trader.scanner --universe b3 --horizonte swing --top 20 --mock --out data/ranking-mock.json

# varredura live (com chaves)
python -m jev_trader.scanner --universe b3 --horizonte swing --top 20 --live --concurrency 8 --enrich

# cron diário
30 18 * * 1-5 cd /Users/jpoloni/dev/jev && .venv/bin/python -m jev_trader.scanner --live --enrich >> logs/scanner.log 2>&1
```

### Custo e latência
- 250 tickers × 1 call × ~1.5k input tokens ≈ 375k tokens/dia; a $0.005/1k ≈ $1.87/dia; com pré-filtro e cache 15min, < $40/mês.
- Latência fase 1 com sem 8: 250/8 ≈ 32 lotes × ~4s/call ≈ 128s + yfinance ≈ 3-4min. Fase 2 (20) adiciona ~40s.

## Work Plan

| Fase | Entregável | Arquivos / Comando | Dep |
|------|-----------|-------------------|-----|
| **1 — Universe** | `universe.py` + `data/universe.json` + teste fallback | `jev_trader/universe.py`, `tests/test_universe.py` (mock B3 403 → fallback Ibov) | — |
| **2 — Scanner core** | `scanner.py` com `scan_one/scan_all/rank/persist`, CLI `--mock` | `jev_trader/scanner.py`, `tests/test_scanner_rank.py` (ordenação + gates) | 1 |
| **3 — Enricher** | Fase 2 Top N com `google_search` stub + re-call | `jev_trader/scanner.py::enrich_top`, `tests/test_scanner_enrich.py` | 2 |
| **4 — ADK tool** | `scan_b3` FunctionTool + registro no `root_agent` + instruções PT-BR | `jev_conversacional/tools/scan_b3_tool.py`, `jev_conversacional/agent.py` | 2 |
| **5 — CLI & Persist** | `ranking-YYYY-MM-DD.json`, `ranking-latest.json`, `ranking.csv`, rotação 30d | `data/`, `scripts/cron_scanner.sh` | 2,3 |
| **6 — Testes E2E** | `tests/e2e/test_e2e_scanner.py` (mock scan 10 tickers) + CI gate | `tests/e2e/test_e2e_scanner.py` | 2,4 |

Cada fase é mergeável isoladamente; 1 e 2 podem ir no mesmo PR.

## Validation Plan

- **Unit (sem rede, sem chave):**
  - `pytest tests/test_universe.py -v` — B3 mock 200 com 5 tickers → parse correto; B3 403 → fallback Ibov 87.
  - `pytest tests/test_scanner_rank.py -v` — mock_answers com `weighted 0.71 compra` deve ficar acima de `0.45 hold`; gate `evento_binario 0.72` força hold e rebaixa no ranking.
  - `pytest tests/test_scanner_cli.py -v` — `python -m jev_trader.scanner --mock --top 5` gera `ranking-mock.json` ordenado e `ranking.csv` com disclaimer.
  - `pytest jev_trader -q` + `pytest -m "not e2e" -q` continuam verdes.

- **Integração mock:**
  - `python -m jev_trader.scanner --universe mock10 --mock --top 5 -v` → 10 calls mock, 5 no ranking, `model=="jev-mock"`, `usage.input_tokens==0`.
  - `python -c "from jev_conversacional.tools.scan_b3_tool import scan_b3; print(scan_b3(top=3))"` → lê cache e retorna PT-BR com `Recomendação:` + `CVM`.

- **Live (com `TYPESAFE_API_KEY`):**
  - `python -m jev_trader.scanner --universe ibov10 --live --top 3 --concurrency 2` → `model startswith jev-`, `sum(prob)≈1`, `weighted` logado.
  - `pytest tests/e2e/test_e2e_scanner.py --env=live -k live -s` → 1 passed live, skip sem chave.

- **Manual ADK:**
  - `adk run jev_conversacional "quais as 10 melhores para swing hoje?"` → chama `scan_b3` e retorna lista ordenada com `Fontes:` (após enrich) e `CVM` em <8s.

**Maior risco de validação:** `sistemaswebb3-listados` mudar contrato (paginação/token). Mitigado com fallback `universe.json` + teste de contrato que falha cedo.

## Risks / Rollback

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| B3 API muda ou bloqueia (403/WAF) | Universe vazio | Fallback `data/universe.json` + allowlist Ibov; log warning; cron não falha |
| Typesafe 429 por concorrência alta | Scan interrompido | Semaphore 6-8 + backoff exponencial + `return_exceptions`; re-tenta só falhas |
| yfinance fora do ar / feriado | `get_market_data` mock | Já tem fallback mock; pré-filtro usa mock sem quebrar |
| Ranking enviesado por `weighted` fixo | Top compras ruins | `weights.yaml` versionado; validar golden set PETR4/VALE3; expor `--weights` para tuning |
| `google_search` quota na fase 2 | Enrich sem fontes | Fase 2 é opcional (`--no-enrich`); stub mock para CI; cache 15min |
| Custo subir com universo cheio | $/mês > esperado | Pré-filtro + `--universe ibov` para daily barato; `ranking-latest.json` evita re-varrer a cada pergunta ADK |

**Rollback:** `git checkout -- jev_conversacional/agent.py` remove `scan_b3` dos tools; `rm -rf data/ranking-*.json` volta a operar ticker-a-ticker; `weights.yaml` anterior restaura ranking.

## Open Questions

- Q1 — `horizonte` default da varredura: `swing (2-8 semanas)` ou `posicional`? Assunção: `swing` (mais sensível a `timing_momentum`). Confirmar com produto.
- Q2 — `top` padrão para ADK: 10 ou 20? Assunção: 10 para resposta caber em janela do Gemini sem truncar.
- Q3 — Fonte alternativa para universo se B3 bloquear: usar `arquivos.b3.com.br` (CSV) ou manter apenas Ibovespa? Assunção: manter snapshot Ibov como fallback contratado.

## Sources

- https://docs.typesafe.ai/introduction/quickstart — `POST /v1/systemone`, `model: jev-latest`, `questions` fan-out, response `model` + `answers` + `usage`
- https://docs.typesafe.ai/concepts/state.md — State objeto nomeado, todos questions veem mesmo state em paralelo
- https://www.b3.com.br/en_us/products-and-services/trading/equities/listed-companies.htm — página oficial empresas listadas B3 (verificada 2026-09-20, conteúdo retornado)
- https://en.wikipedia.org/wiki/B3_(stock_exchange) — 475 empresas listadas em 10/2022, tickers 4 letras + número (verificado)
- https://github.com/wilsonfreitas/brasa/blob/HEAD/docs/CONFIGURATION.md — uso de `https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany` como fonte B3 pública (verificado, contém URL base)
- Repo local: `jev_trader/state.py`, `questions.py` (9 perguntas), `composer.py` + `weights.yaml` (0.30/0.25/0.15/0.15/0.15, thresholds 0.62/0.38), `client.py` (1 call/ticker), `jev_conversacional/agent.py` (gemini-3.8-flash, 4 tools), `tools/market_data.py` (cache 15min, yfinance fallback)

---
*Spec elaborada após inspeção direta do workspace e fontes primárias em 2026-09-20. Aguardar aprovação para implementar.*
