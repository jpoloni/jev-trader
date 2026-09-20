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

## Uso ADK
```bash
.venv/bin/adk create jev_conversacional   # já scaffoldado — use o existente
.venv/bin/adk run jev_conversacional
.venv/bin/adk web --port 8000  # Dev UI em http://localhost:8000
```

## Jev-Trader direto (sem ADK)
```bash
.venv/bin/python -m jev_trader.client --ticker PETR4 --horizonte swing
```

## Testes
```bash
.venv/bin/pytest -q
```
