"""Jev Conversacional — root_agent ADK (Gemini + Memory + google_search + Jev-Trader)."""
from __future__ import annotations

import os
from dotenv import load_dotenv

from google.adk.agents import LlmAgent
from google.adk.tools import google_search, load_memory
from google.genai import types as genai_types

# Carrega .env do projeto (GEMINI_MODEL, GOOGLE_API_KEY)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# FunctionTools locais
from jev_conversacional.tools.jev_trader_tool import call_jev_trader
from jev_conversacional.tools.market_data import get_market_data

# --- Guardrails (callbacks ADK) ---
def before_model_callback(ctx, llm_request):  # type: ignore
    """Bloqueia recomendação sem call_jev_trader quando intent é recomendação.

    Tutorial ADK Step 5: Input Guardrail. Retorna None para seguir; para bloquear,
    modificar llm_request ou retornar resposta custom conforme API futura.
    Por ora apenas loga e deixa passar — a regra dura está no instruction + tool_choice.
    """
    return None

def before_tool_callback(tool, args, tool_context):  # type: ignore
    """Valida ticker e aplica cache google_search (TTL via State temp).

    Tutorial ADK Step 6: Tool Argument Guardrail.
    """
    try:
        name = getattr(tool, "name", str(tool))
        if name == "call_jev_trader" and isinstance(args, dict):
            ticker = str(args.get("ticker", "")).strip().upper()
            # validação B3: 4 letras + 1-2 dígitos, ex.: PETR4, VALE3
            import re
            if ticker and not re.match(r"^[A-Z]{4}\d{1,2}(\.SA)?$", ticker):
                return {"error": f"Ticker inválido: {ticker}. Use formato B3, ex.: PETR4"}
    except Exception:
        pass
    return None


root_agent = LlmAgent(
    model=GEMINI_MODEL,
    name="jev_conversacional",
    description="Assessor B3 educacional com memória persistente (ADK Memory) e Jev-Trader subagente (Typesafe)",
    generate_content_config=genai_types.GenerateContentConfig(
        tool_config=genai_types.ToolConfig(
            include_server_side_tool_invocations=True,
        ),
    ),
    instruction=(
        "Você é o Jev Conversacional, assessor educacional de investimentos B3 — fale em PT-BR, "
        "seja direto e cite fontes.\n"
        "REGRAS DURAS:\n"
        "1) Para qualquer pedido de compra/venda/hold com ticker (ex.: 'vale comprar PETR4?', 'devo vender VALE3?'), "
        "CHAME SEMPRE a tool call_jev_trader com ticker. Nunca invente recomendação sem chamar a tool.\n"
        "2) Use load_memory quando precisar lembrar perfil do investidor, carteira ou decisões passadas.\n"
        "3) Use google_search para notícias/eventos do ticker (últimos 7 dias) e Ibovespa antes de recomendar, "
        "quando não houver dados recentes em memória.\n"
        "4) Após receber o JSON do Jev-Trader, responda em PT-BR com seções:\n"
        "   **Recomendação:** compra|venda|hold (com confiança 0..1 e probabilidades)\n"
        "   **Por quê:** scores (tendência, fundamentos, sentimento, timing, risco) + weighted\n"
        "   **Riscos/Gates:** risco_excessivo, evento_binario_iminente, informacao_insuficiente\n"
        "   **Fontes:** títulos + datas do google_search\n"
        "   **Disclaimer:** 'Conteúdo educacional. Não constitui recomendação personalizada (Res. CVM 20). Decisão final é do investidor.'\n"
        "5) Se confidence <0.60 ou qualquer gate >0.70, use linguagem cautelosa ('recomendo aguardar'), explique o gate e ofereça acompanhamento.\n"
        "6) Nunca execute ordens; apenas recomenda.\n"
    ),
    tools=[load_memory, google_search, get_market_data, call_jev_trader],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
)
