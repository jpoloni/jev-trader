# Jev — Trader + Conversacional (Google ADK × Typesafe)

Agente B3 com **Google ADK** (Gemini + Session/Memory + google_search) orquestrando o **Jev-Trader** (Typesafe `jev-latest`, 9 perguntas paralelas) para `compra|venda|hold`.

## Estrutura
```
jev/
  jev_trader/            # System One — state, questions, composer, weights
  jev_conversacional/    # ADK — root_agent, tools, callbacks
  tests/                 # golden + unit
  docs/plans/            # specs
```

## Setup
```bash
uv venv --python 3.11
uv pip install -e . --no-cache
cp jev_conversacional/.env.example jev_conversacional/.env
# edite GOOGLE_API_KEY e TYPESAFE_API_KEY
```

> **Dados confiáveis:** se o yfinance falhar, a cotação vem como indisponível (`disponivel=False`) — nunca um preço inventado.
> Para demos offline, use `JEV_MARKET_MOCK=1` (dados fixos, marcados como `simulado`).
> Em modo `--live`, falhas da Typesafe deixam o ticker fora do ranking e são listadas no stderr; não há fallback para respostas simuladas.

## Uso Conversacional (Jev CLI Executivo)
```bash
# Chat interativo no terminal (sem ruído de logs, design limpo com cores e tabelas)
./jev

# Consulta direta one-shot
./jev "vale comprar PETR4?"
./jev "quais as 5 melhores ações para swing hoje?"

# Gestão de Carteira Pessoal e P&L
./jev "comprei 100 PETR4 a R$ 42,00"
./jev "como está minha carteira hoje?"
./jev "qual meu P&L atual?"

# Comparativo Direto Lado a Lado
./jev "qual comprar: PETR4 ou VALE3?"

# Web Dev UI
.venv/bin/adk web --port 8000  # Dev UI em http://localhost:8000
```

## Jev-Trader & Scanner Direto (System One)
```bash
# Análise detalhada de ativo com card visual
.venv/bin/python -m jev_trader.client --ticker PETR4 --mock

# Varredura e ranking de mercado (85 ativos do IBOV)
.venv/bin/python -m jev_trader.scanner --universe ibov --mock --top 10
```

## Testes
```bash
.venv/bin/python -m pytest -m "not e2e" -q
.venv/bin/python -m pytest tests/e2e -m e2e --env=mock -q
```

## 🗺️ Roadmap & Próximos Passos
O roadmap estratégico com cronograma de sprints e detalhamento arquitetural das próximas fases está documentado em:
* [docs/roadmap.md](file:///Users/jpoloni/dev/jev/docs/roadmap.md)
  * **v0.4 (Q4 2026):** Motor de Alertas & Monitoramento Contínuo (`data/alerts.json` + Daemon CLI).
  * **v1.0 (Q1 2027):** Dashboard Web Interativo (Vite + React + TradingView Charts) e Backtesting Engine.
  * **v1.1 (Q2 2027):** Suporte Multi-Mercado (NYSE/NASDAQ) e Arquitetura Multi-Agent ADK.

## 📋 Documentação & Handoffs
* [Handoff — 26/09/2026](file:///Users/jpoloni/dev/jev/docs/handoff-2026-09-26.md): Entrega das Fases 1 e 2 (Fundamentos, News Feed, Indicadores, Carteira, SQLite e Comparador).
* [Handoff — 20/09/2026](file:///Users/jpoloni/dev/jev/docs/handoff-2026-09-20.md): Versão inicial de integração ADK + Typesafe e Scanner B3.

