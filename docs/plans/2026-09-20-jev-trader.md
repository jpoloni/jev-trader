# Jev-Trader — Spec de Agente de Recomendação compra/venda/hold com Typesafe Jev

## Goal
Construir o agente **Jev-Trader**: um serviço que, dado um ativo de bolsa (ticker), contexto de mercado e perfil do usuário, recomenda **compra / venda / hold** usando o modelo **Jev (System One)** da Typesafe via API `POST /v1/systemone`. O agente deve ser determinístico em código, auditável, com probabilidades calibradas e *confidence-gating* — Jev faz julgamentos atômicos e rápidos, o código decide.

## Success Criteria
- [ ] Uma chamada `POST https://api.typesafe.ai/v1/systemone` com `model: jev-latest` retorna recomendação tipada (`compra|venda|hold`) com `probabilities` + `confidence`, e justificativa derivada de scores atômicos.
- [ ] Custo/latência por decisão ≈ 1 chamada (fan-out paralelo) independente do nº de perguntas; sem chamadas sequenciais encadeadas por falta de decomposição.
- [ ] Regra de segurança: se `confidence < threshold` ou `noul(risco_excessivo) > 0.7` ou `noul(evento_binario_iminente) > 0.65`, o sistema degrada para `hold` + alerta humano, nunca emite `compra/venda` confiante em baixa certeza.
- [ ] 100% das respostas incluem disclaimer CVM ("não constitui recomendação vinculante; finalidade educacional") e são logáveis para auditoria.
- [ ] Playbook validado com 30 casos históricos (15 alta/baixa/neutro) com taxa de concordância com analista humano > 70% nos casos de alta confiança.

## Context And Current Facts

**O que é Typesafe / Jev (fatos verificados na doc):**
- **System One**: Jev é o modelo flagship System One — decisões rápidas e estruturadas para software, não chat generativo. Código fica no controle; Jev responde julgamentos estreitos.
- **API**: `POST https://api.typesafe.ai/v1/systemone` com `Authorization: Bearer <API_KEY>`, body `{ state, model: "jev-latest", questions: { id: { type, instructions, criteria } } }`. Response `{ model: "jev-1.13.0", answers: { id: { type, choice/score/noul, probabilities, confidence, legend } }, usage }`.
- **State**: pode ser `string` ou `object` JSON com campos nomeados; objeto é preferido para maioria dos casos para manter relações claras. Todo `questions` de um request vê o mesmo `state` e é avaliado em paralelo, independentemente. Texto apenas; imagens/áudio/vídeo não suportados. Idioma primário é inglês, outras línguas aceitas com menor acurácia.
- **Primitives**: 3 tipos — `Choice` (qual opção de um conjunto sem ordem, retorna `choice`+`probabilities`+`confidence`), `Score` (posição em espectro ordenado com níveis descritos, retorna `score` fracionário + `legend` + `probabilities` + `confidence`), `Noul` (probabilidade yes 0..1, sem `confidence` separado; 0.5 = incerteza máxima). Cada pergunta tem `id` (para código), `type`, `instructions` (pergunta completa), e `criteria` (opções/níveis).
- **Composição em código**: 1 julgamento atômico por pergunta; se julgamento depende de fatores independentes, quebrar em perguntas separadas e combinar com pesos no código (Composite Scoring). Pesos ficam em código para ajuste sem reescrever prompt.
- **Padrões**: `Speculative fan-out` (enviar muitas perguntas juntas, ignorar as irrelevantes; custo extra é só tokens, latência quase não muda), `Confidence-gated routing` (resposta diz *o quê*, confidence diz *se deve agir*), `Composite scoring` (combinar scores atômicos com pesos).
- **Referência por path**: ao usar state estruturado, referir campos com `` `campo.subcampo[i].texto` `` dentro de `instructions` para ancorar julgamento.

**Workspace atual:**
- Diretório `/Users/jpoloni/dev/jev` vazio (greenfield, sem código prévio). Sem convenção de planos prévia; será criado `docs/plans/`.

**Domínio bolsa:**
- Recomendação compra/venda/hold é regulada (CVM) — exige disclaimer, não pode executar ordem automaticamente sem consentimento, precisa trilha de auditoria, e deve distinguir análise técnica vs fundamentalista vs sentimento.

## Constraints And Non-goals

**Constraints:**
- Não executar ordens: Jev-Trader recomenda, não opera. Integração com corretora é fase futura e exige consentimento explícito.
- Não pedir a Jev "analise tudo e decida" em uma pergunta monolítica — viola princípio "one snap judgment per question". Decompor.
- State textual apenas; candles/indicadores devem ser serializados como texto/JSON (ex.: lista de fechamentos, RSI=68.2), não imagem de gráfico.
- Instruções preferencialmente em inglês para maior acurácia (documentado que inglês é primário), mesmo que `criteria` e `state` contenham PT-BR. Alternativa PT-BR integral é aceita com queda esperada de precisão — decisão explícita abaixo.
- Toda recomendação deve respeitar LGPD (não logar dados sensíveis sem anonimização) e incluir disclaimer educacional.

**Non-goals (fora do escopo v1):**
- Execução automática de ordens, backtesting automatizado contínuo, carteira multi-ativo com otimização Markowitz, chatbot conversacional, fine-tuning de Jev.

## Key Decisions

| # | Decisão | Recomendação | Alternativa rejeitada | Por quê |
|---|---------|--------------|----------------------|---------|
| 1 | **Decomposição vs pergunta única** | 5 Scores + 3 Nouls + 1 Choice em 1 chamada, composição em código (Composite Scoring) | 1 Choice `compra|venda|hold` monolítico com prompt longo | Monolito esconde pesos, não permite ajuste fino, viola "one snap judgment per question"; composite permite pesos versionáveis e auditáveis. |
| 2 | **Escolha da primitiva para decisão final** | Final em **código** a partir de weighted score, mas manter **Choice `recomendacao`** como validação e fonte de `confidence` (speculative fan-out) | Só Choice ou só Score agregado | Ter ambos dá duplo sinal: código é autoritativo e auditável; Choice fornece probabilidade calibrada e `confidence` nativo para gating sem custo extra. |
| 3 | **Confidence gating** | Thresholds: `Choice.confidence < 0.60 => hold + review_humano`; `Noul(risco_excessivo) > 0.70 => hold` | Ignorar confidence e agir sempre na probabilidade máxima | Padrão Confidence-gated routing: probabilidade diz *qual*, confidence diz *se deve agir*. Evita recomendações confiantemente erradas em regime de incerteza. |
| 4 | **Fan-out especulativo** | Enviar todas 9 perguntas sempre, código ignora irrelevantes (ex.: se sem notícias, ignora `sentimento_noticia`) | Duas chamadas sequenciais condicionais | Doc mostra 13 perguntas em 1 chamada é 11.5x mais barato e 9.6x mais rápido que 13 chamadas; perguntas extras custam só tokens. |
| 5 | **Idioma das instructions** | **Inglês** para `instructions` de maior precisão, `criteria` e `state` em PT-BR/EN misto | Tudo em PT-BR | Doc: Jev primariamente treinado em inglês, outras línguas com menor acurácia. Manter instructions em inglês maximiza calibração; dados do ativo permanecem em PT-BR sem perda. |
| 6 | **Referência de campos** | Usar paths com backticks `` `mercado.candles_14d` `` dentro de `instructions` | Pergunta genérica "analise o estado" | Ancoragem explícita reduz alucinação e segue guia "Reference specific fields". |
| 7 | **State como string vs objeto** | **Objeto JSON nomeado** com 6 chaves de topo | String concatenada de relatório | Objeto preserva relações (ticket vs order no exemplo da doc); facilita `instructions` apontarem ao campo certo e reuso em follow-ups. |
| 8 | **SDK** | `typesafe-sdk` Python (`TypeSafeClient`, `Choice`, `Score`, `Noul`) + fallback cURL | Só HTTP cru | Tipagem `response.answers[id].choice/score/noul/confidence` elimina parsing frágil de texto. |

## Recommended Approach

### 1. Arquitetura (código no controle)

```
[Fontes] -> Normalizador -> State (JSON) -> Jev System One (1 chamada, 9 perguntas paralelas) -> Composer (pesos + gates) -> Saída tipada {recomendacao, confidence, probabilidades, justificativa, disclaimer}
                |-> cálculo de indicadores (RSI, MACD, médias) em código (não pedir a Jev para calcular)
```

**Princípio:** Cálculo numérico e regras de negócio ficam em Python; Jev apenas julga padrões/narrativas ("tendência parece de alta dado `mercado.candles`?").

### 2. State — esquema canônico (objeto)

```json
{
  "ativo": { "ticker": "PETR4", "nome": "Petrobras PN", "setor": "Petróleo & Gás", "bolsa": "B3" },
  "mercado": {
    "preco_atual": 38.42,
    "variacao_dia_pct": -1.2,
    "volume_vs_media_20d": 1.35,
    "candles_14d": [{"data":"2026-09-05","fechamento":36.1}, "..."],
    "indicadores": {"rsi_14": 68.2, "macd_hist": 0.12, "mm_20_vs_50": "mm20 acima mm50", "suporte": 36.8, "resistencia": 39.5, "volatilidade_20d_pct": 2.8},
    "tendencia_descritiva": "Alta de 3 pregões com volume crescente, RSI próximo de sobrecompra"
  },
  "fundamentos": {"pl": 4.2, "dy_12m_pct": 12.1, "roe_pct": 18.3, "divida_liquida_ebitda": 1.1, "resultado_ultimo_tri": "lucro +8% YoY, guidance mantido"},
  "contexto": {
    "noticias_7d": ["Petrobras anuncia reajuste diesel +2% (Reuters 19/09)", "Brent +1.5% na semana"],
    "eventos_proximos": ["Resultado Q3 em 07/11", "Reunião Copom 20/09"],
    "sentimento_mercado": "Ibov +0.6% no dia, setor petróleo outperform"
  },
  "posicao_usuario": {"tem_posicao": true, "preco_medio": 35.0, "pct_carteira": 8.5, "horizonte": "swing (2-8 semanas)", "perfil_risco": "moderado"},
  "restricoes": {"disclaimer": "Análise educacional, não é recomendação de investimento personalizada (CVM)"}
}
```

Campos são texto/número; candles serializados como lista curta (14-20 pontos) para caber em tokens. Nunca enviar imagem.

### 3. Questions — 9 perguntas em 1 chamada

Todas `instructions` em inglês (precisão), referenciando paths com backticks.

**Scores (espectro ordenado, 5 níveis salvo risco com 4):**

```python
from typesafe_sdk import Choice, Noul, Score

questions = {
  "tendencia_tecnica": Score(
    instructions="Given `mercado.candles_14d`, `mercado.indicadores` and `mercado.tendencia_descritiva`, how strong is the technical trend?",
    criteria=[
      "Strong downtrend — clear lower highs/lows, momentum negative",
      "Weak downtrend — slight negative bias",
      "Neutral / sideways — no clear direction",
      "Weak uptrend — slight positive bias",
      "Strong uptrend — clear higher highs/lows, momentum positive"
    ]
  ),
  "qualidade_fundamentalista": Score(
    instructions="Given `fundamentos` and `ativo.setor`, how strong are fundamentals for a 2-8 week horizon?",
    criteria=[
      "Very weak — expensive or deteriorating, high leverage",
      "Weak — below sector average",
      "Average — fair valuation, stable",
      "Strong — attractive valuation and solid profitability",
      "Very strong — cheap, highly profitable, low leverage"
    ]
  ),
  "risco_volatilidade": Score(
    instructions="Given `mercado.indicadores.volatilidade_20d_pct`, `mercado.volume_vs_media_20d`, `contexto.eventos_proximos` and `posicao_usuario.pct_carteira`, what is downside risk/volatility?",
    criteria=[
      "Low risk — low vol, no near catalyst, small position",
      "Moderate risk",
      "High risk — elevated vol or large position or near event",
      "Extreme risk — very high vol and binary event imminent"
    ]
  ),
  "sentimento_noticia": Score(
    instructions="Given `contexto.noticias_7d` and `contexto.sentimento_mercado`, what is news/sentiment tone for `ativo.ticker`?",
    criteria=[
      "Very negative — multiple adverse catalysts",
      "Slightly negative",
      "Neutral / mixed",
      "Slightly positive",
      "Very positive — clear tailwinds"
    ]
  ),
  "timing_momentum": Score(
    instructions="Given `mercado.indicadores.rsi_14`, `mercado.variacao_dia_pct` and `mercado.indicadores.mm_20_vs_50`, is timing stretched?",
    criteria=[
      "Deeply oversold — contrarian buy timing",
      "Oversold — favorable for entry",
      "Neutral — no timing edge",
      "Overbought — unfavorable for entry",
      "Deeply overbought — high pullback risk"
    ]
  ),
  # Nouls — gates de risco
  "risco_excessivo": Noul(
    instructions="Does `mercado` + `contexto.eventos_proximos` + `posicao_usuario` indicate that a new buy would risk a disproportionate loss vs expected gain?"
  ),
  "informacao_insuficiente": Noul(
    instructions="Is `fundamentos` or `contexto.noticias_7d` missing or contradictory to the point that a buy/sell decision would be a guess?"
  ),
  "evento_binario_iminente": Noul(
    instructions="Is there a binary event in `contexto.eventos_proximos` within ~10 days that makes direction highly uncertain (earnings, Copom, etc.)?"
  ),
  # Choice — recomendação direta (speculative, para confidence)
  "recomendacao": Choice(
    instructions="Given all fields in state, which action best fits a `posicao_usuario.horizonte` and `posicao_usuario.perfil_risco` investor?",
    criteria={
      "compra": "Open or increase long position now — risk/reward favors entry",
      "venda": "Close or reduce position now — risk/reward favors exit",
      "hold": "Do nothing — wait for better price or more information"
    }
  )
}
```

**Por que estes tipos:**
- `Score` para espectro (tendência, fundamentos) — permite score fracionário (ex.: 3.4 entre neutro e alta fraca) e `confidence` por distribuição.
- `Noul` para gatilhos binários de bloqueio — probabilidade direta para `if noul > threshold`.
- `Choice` para decisão categórica sem ordem — retorna `choice` + distribuição + `confidence`.

### 4. Composer — lógica em código (pseudocódigo)

```python
# normaliza scores 0..1
def norm(score, levels): return score / (len(levels)-1)

w = {"tendencia":0.30, "fundamentos":0.25, "sentimento":0.15, "timing_inv":0.15, "risco_inv":0.15}
# timing: oversold é bom para compra, overbought ruim -> inverter se for compra
timing_buy = 1 - norm(timing_momentum.score, 5)  # oversold=0 -> 1.0
risco_inv = 1 - norm(risco_volatilidade.score, 4)

weighted = (
  w["tendencia"]*norm(tendencia_tecnica.score,5) +
  w["fundamentos"]*norm(qualidade_fundamentalista.score,5) +
  w["sentimento"]*norm(sentimento_noticia.score,5) +
  w["timing_inv"]*timing_buy +
  w["risco_inv"]*risco_inv
)
# mapeia para recomendação bruta
if weighted >= 0.62: raw = "compra"
elif weighted <= 0.38: raw = "venda"
else: raw = "hold"

# gates (Noul) — soberanos
if risco_excessivo.noul > 0.70 or evento_binario_iminente.noul > 0.65 or informacao_insuficiente.noul > 0.68:
    final = "hold"; motivo_gate = True
elif recomendacao.confidence < 0.60:
    final = "hold"; motivo_gate = True
else:
    # se Choice discorda fortemente do weighted e tem alta confidence, preferir hold para revisão
    if recomendacao.choice != raw and recomendacao.confidence > 0.75:
        final = "hold"
    else:
        final = raw

saida = {
  "ticker": state["ativo"]["ticker"],
  "recomendacao": final,
  "confidence": recomendacao.confidence,
  "probabilidades": recomendacao.probabilities,
  "scores": {...},
  "gates": {"risco_excessivo": risco_excessivo.noul, ...},
  "justificativa": f"Tendência {tendencia_tecnica.score:.1f}/4, fundamentos {qualidade_fundamentalista.score:.1f}/4 ...",
  "disclaimer": "Conteúdo educacional. Não constitui recomendação personalizada (Res. CVM 20). Decisão final é do investidor."
}
```

Pesos `w` ficam em config versionada (`jev_trader_weights.yaml`) — ajuste sem tocar prompt.

### 5. Chamada — SDK e cURL

```python
from typesafe_sdk import TypeSafeClient
client = TypeSafeClient()  # lê TYPESAFE_API_KEY
resp = client.system_one(state=state, questions=questions, model="jev-latest")
# uso: resp.answers["recomendacao"].choice, .confidence, .probabilities
#      resp.answers["tendencia_tecnica"].score
#      resp.answers["risco_excessivo"].noul
```

```bash
curl -X POST https://api.typesafe.ai/v1/systemone \
  -H "Authorization: Bearer $TYPESAFE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"state": {...}, "model": "jev-latest", "questions": {"tendencia_tecnica": {"type":"score","instructions":"...","criteria":[...]}}}'
```

### 6. Observabilidade
- Logar `model` retornado (ex.: `jev-1.13.0`), `usage.input_tokens/output_tokens`, todas `probabilities` e `confidence`, e pesos usados.
- Métrica: distribuição de `recomendacao.choice` vs `final` pós-gates, taxa de `hold` por baixa confiança.

## Work Plan

| Fase | Entregável | Detalhe | Dependência |
|------|-----------|---------|-------------|
| **1 — Fundação** | `jev_trader/state.py` + `indicadores.py` | Normaliza candles, calcula RSI/MACD/MM em código (biblioteca `ta` ou puro), serializa State canônico; testes com fixtures PETR4/VALE3. | — |
| **2 — Contrato Typesafe** | `jev_trader/questions.py` | Define as 9 perguntas acima como objetos `Choice/Score/Noul` com instructions em inglês + backticks; validador de State (JSON schema). | 1 |
| **3 — Composer & Gates** | `jev_trader/composer.py` + `weights.yaml` | Implementa `compose(answers)->saida` com pesos, thresholds, justificativa textual e disclaimer; exports `confidence <0.6 => hold`. | 2 |
| **4 — Cliente & CLI** | `jev_trader/client.py` + `cli.py` | `TypeSafeClient` wrapper, retry com backoff, leitura `TYPESAFE_API_KEY`; CLI `jev-trader --ticker PETR4 --horizonte swing`. | 3 |
| **5 — API / Serviço** | `app.py` (FastAPI) | Endpoint `POST /recomendacao` recebendo State parcial, retornando saída tipada + auditoria; healthcheck. | 4 |
| **6 — Validação & Docs** | Golden set + `docs/jev-trader.md` | 30 casos históricos com rótulo humano; README com exemplo cURL/SDK/Playground. | 5 |

Ordem é sequencial curta; fases 1-3 cabem em 1 PR, 4-5 em outro.

## Validation Plan

- **Unitário (focado):**
  - `pytest jev_trader/test_state.py` — State serializa sem imagem, candles truncados corretamente.
  - `pytest jev_trader/test_composer.py` — Dado `answers` mockado com `recomendacao.confidence=0.45`, Composer retorna `hold` (gate); `risco_excessivo.noul=0.82` força `hold` mesmo com weighted alto.
  - `pytest jev_trader/test_questions.py` — snapshots das 9 instruções garantem backticks e `criteria` ordenado (Score) / sem ordem (Choice).
- **Integração (requer API key):**
  - `python -m jev_trader.client --dry-run` com State fixture chama `client.system_one` real; assert `resp.model startswith "jev-"` e `answers` contém as 9 chaves tipadas.
  - Comparar `curl` vs SDK no mesmo State — probabilidades devem coincidir dentro de tolerância (Jev determinístico para mesma entrada).
- **Playground:**
  - Colar State JSON no [Playground](https://console.typesafe.ai/playground) com as 9 perguntas e verificar visualmente que `Choice.recomendacao.probabilities` soma 1 e `Score.legend` reflete níveis.
- **Golden set (E2E):**
  - Pasta `fixtures/golden/` com 30 JSONs (state + rótulo humano compra/venda/hold). Rodar `scripts/eval_golden.py` e checar concordância >70% nos casos `confidence>=0.65`.
- **Manual / compliance:**
  - Verificar disclaimer presente em toda resposta e log sem PII.

**Maior risco de validação:** Golden set enviesado por regime de mercado único. Mitigar incluindo 10 casos de cada regime (alta, baixa, lateral) e 5 com evento binário iminente.

## Risks / Rollback

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Jev com baixa acurácia em PT-BR ou jargão B3 | Recomendação errada confiante | Instructions em inglês + `criteria` bilíngue; sempre exigir `confidence` alto para agir; fallback `hold` |
| Alucinação se State virar blob de texto | Perda de ancoragem | State objeto + instructions com backticks obrigatórios; linter que falha se `instructions` não contém `` ` `` |
| Volatilidade extrema gera `compra` em topo | Perda financeira | Gate `risco_excessivo` soberano + `timing_momentum` penaliza sobrecompra; limite `pct_carteira` no State |
| Vazamento de chave API | Abuso | `TYPESAFE_API_KEY` só via env/secret manager; nunca logar |
| Mudança de modelo `jev-latest` | Drift de probabilidades | Pinar `model` no log; teste de regressão no golden set a cada release; permitir override `jev-1.13.0` |
| Uso como recomendação vinculante (CVM) | Risco regulatório | Disclaimer obrigatório, saída rotulada `educacional`, trilha de auditoria, nunca auto-executar ordem |

**Rollback:** Composer é feature-flag `USE_JEV_TRADER_V1`. Se taxa de `hold` por baixa confiança >60% ou reclamações, reverter pesos para versão anterior via `weights.yaml` sem deploy de código.

## Open Questions

- **Q1 — Fonte de dados de mercado em tempo real para `mercado.candles_14d` e `indicadores`:** B3 / Yahoo Finance / provedor pago? Assunção atual: Yahoo Finance gratuito para v1, com cache de 15min. Confirmar com produto.
- **Q2 — Pesos iniciais `w`:** Valores acima são proposta (0.30/0.25/0.15/0.15/0.15). Validar com analista quant se tendência deve pesar mais que fundamentos em swing trade.
- **Q3 — Thresholds de confidence/Noul:** 0.60 / 0.70 propostos a partir de exemplos da doc (confidence ~0.78 no exemplo técnico). Calibrar no golden set; exposição como config?

## Sources

- https://docs.typesafe.ai/introduction/quickstart — endpoint `POST /v1/systemone`, `model: jev-latest`, estrutura `state`+`questions`, exemplo de `Choice`/`Score`/`Noul` e `response.answers` com `probabilities`/`confidence`/`noul`, SDK `typesafe_sdk` e `TypeSafeClient`
- https://docs.typesafe.ai/concepts/state.md — State como string/objeto/array, objeto nomeado preferido, todos questions veem mesmo state, texto apenas, inglês primário
- https://docs.typesafe.ai/primitives.md — 3 primitivas, `type`/`instructions`/`criteria`, `id` não vai ao modelo, escolher tipo pelo formato da resposta, `probabilities`+`confidence`, independência e paralelismo, speculative fan-out e composite scoring
- https://docs.typesafe.ai/primitives/choice.md — Choice para opção de conjunto, `choice`+`probabilities`+`confidence`
- https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md — código no controle, julgamentos estreitos, não pedir análise monolítica
- https://docs.typesafe.ai/patterns.md — catálogo de padrões System One
- https://docs.typesafe.ai/patterns/composite-scoring.md — quebrar julgamento complexo em scores atômicos e combinar com pesos em código
- https://docs.typesafe.ai/patterns/confidence-routing.md — `confidence` como segundo eixo (o que vs se deve agir)
- https://docs.typesafe.ai/confidence.md — `confidence` derivado de `probabilities` (`(n*peak-1)/(n-1)`), diferença de `probabilities`, uso para escalar para humano
- https://docs.typesafe.ai/llms.txt — índice completo da doc (descoberta)

---
*Spec gerada a partir de inspeção direta da doc Typesafe em 2026-09-20. Não executar implementação até aprovação.*
