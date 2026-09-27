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
.venv/bin/python -m pytest tests/e2e -m e2e --env=mock --ignore=tests/e2e/test_e2e_web.py -q
```

