"""compare_tickers — FunctionTool ADK para comparação lado a lado de ativos B3."""
from __future__ import annotations

from typing import Any
from .jev_trader_tool import call_jev_trader


def compare_tickers(
    tickers: list[str],
    horizonte: str | None = None,
) -> dict[str, Any]:
    """Compara 2 a 4 ações da B3 lado a lado em termos técnicos, fundamentalistas e de risco.

    Use quando o usuário pedir comparações como:
    - 'Qual comprar: PETR4 ou VALE3?'
    - 'Compare ITUB4 com BBDC4'
    - 'Entre WEGE3 e PRIO3, qual tem melhor relação risco/retorno?'

    Args:
        tickers: Lista de tickers B3 a comparar (ex: ['PETR4', 'VALE3'])
        horizonte: Horizonte operacional ('swing', 'daytrade', 'posicional')

    Returns:
        dict com tabela comparativa, scores de cada dimensão, gates e recomendação relativa.
    """
    if not tickers or len(tickers) < 2:
        return {"error": "Informe pelo menos 2 tickers para comparação."}

    # Limita a 4 tickers para manter a resposta concisa e de alto valor
    clean_tickers = [t.upper().strip() for t in tickers[:4] if t.strip()]

    comparativo = []
    for t in clean_tickers:
        try:
            res = call_jev_trader(ticker=t, horizonte_override=horizonte)
            state = res.get("state", {})
            mercado = state.get("mercado", {})
            fundamentos = state.get("fundamentos", {})
            scores = res.get("scores", {})

            comparativo.append({
                "ticker": t,
                "nome": state.get("ativo", {}).get("nome", t),
                "setor": state.get("ativo", {}).get("setor", "Não informado"),
                "preco_atual": mercado.get("preco_atual"),
                "recomendacao": res.get("recomendacao", "hold"),
                "score_ponderado": res.get("weighted", 0.0),
                "confianca": res.get("confidence", 0.0),
                "probabilidades": res.get("probabilidades", {}),
                "scores": scores,
                "multiplos": {
                    "pl": fundamentos.get("pl_trailing"),
                    "pvp": fundamentos.get("pvp"),
                    "roe_pct": fundamentos.get("roe_pct"),
                    "dy_pct": fundamentos.get("dividend_yield_pct"),
                },
                "indicadores": {
                    "rsi": mercado.get("indicadores", {}).get("rsi_14"),
                    "volatilidade": mercado.get("indicadores", {}).get("volatilidade_20d_pct"),
                },
                "motivo_gate": res.get("motivo_gate"),
                "simulado": bool(res.get("simulado")),
                "cotacao_disponivel": bool(res.get("dados_mercado", {}).get("disponivel")),
            })
        except Exception as e:
            comparativo.append({
                "ticker": t,
                "error": f"Falha ao analisar {t}: {e}",
            })

    # Ordena ativos válidos por score ponderado descrescente
    validos = [c for c in comparativo if "score_ponderado" in c]
    ordem_rec = {"compra": 0, "hold": 1, "venda": 2}
    validos.sort(key=lambda x: (ordem_rec.get(x["recomendacao"], 9), -x["score_ponderado"], -x["confianca"]))

    vencedor = validos[0]["ticker"] if validos else None

    simulados = [c["ticker"] for c in validos if c.get("simulado")]
    aviso = None
    if simulados:
        aviso = (
            "Comparação com análises SIMULADAS (sem TYPESAFE_API_KEY) para " + ", ".join(simulados)
            + " — não representa análise real; informe isso ao usuário."
        )

    return {
        "horizonte": horizonte or "swing",
        "total_comparados": len(clean_tickers),
        "melhor_ativo": vencedor,
        "comparativo": comparativo,
        "ranking_relativo": [v["ticker"] for v in validos],
        "simulado": bool(simulados),
        "aviso": aviso,
    }
