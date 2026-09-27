"""manage_portfolio — FunctionTool ADK para gestão da carteira do investidor."""
from __future__ import annotations

from typing import Any
from jev_trader.portfolio import (
    buy_asset,
    sell_asset,
    get_position,
    get_portfolio_summary,
    load_trade_history,
)


def manage_portfolio(
    acao: str,
    ticker: str | None = None,
    quantidade: int | None = None,
    preco: float | None = None,
    notas: str | None = None,
) -> dict[str, Any]:
    """Gerencia a carteira de investimentos pessoal do usuário.

    Use quando o usuário informar compras ou vendas de ações, perguntar sobre seu
    patrimônio, P&L (lucro/prejuízo), alocação de ativos ou histórico de trades.

    Args:
        acao: 'comprar' | 'vender' | 'resumo' | 'posicao' | 'historico'
        ticker: Código da ação B3 (ex: PETR4, VALE3) — obrigatório para comprar, vender e posicao
        quantidade: Número de ações — obrigatório para comprar e vender
        preco: Preço de execução por ação (R$) — obrigatório para comprar e vender
        notas: Anotações opcionais (ex: 'alvo R$ 52, stop R$ 45')

    Returns:
        dict estruturado com os dados atualizados da operação ou da carteira.
    """
    acao = (acao or "resumo").strip().lower()

    if acao in ("comprar", "buy", "compra", "adicionar"):
        if not ticker:
            return {"error": "Ticker é obrigatório para registrar compra."}
        if not quantidade or quantidade <= 0:
            return {"error": "Quantidade de ações deve ser maior que zero."}
        if not preco or preco <= 0:
            return {"error": "Preço da ação deve ser maior que zero."}
        pos = buy_asset(ticker=ticker, quantidade=quantidade, preco=preco, notas=notas)
        summary = get_portfolio_summary()
        return {
            "status": "sucesso",
            "mensagem": f"Compra de {quantidade} {ticker.upper()} a R$ {preco:.2f} registrada com sucesso!",
            "posicao_atualizada": pos,
            "resumo_carteira": {
                "patrimonio_total": summary["patrimonio_total"],
                "total_investido": summary["total_investido"],
                "pl_total_pct": summary["pl_total_pct"],
            },
        }

    elif acao in ("vender", "sell", "venda", "remover"):
        if not ticker:
            return {"error": "Ticker é obrigatório para registrar venda."}
        if not quantidade or quantidade <= 0:
            return {"error": "Quantidade de ações deve ser maior que zero."}
        if not preco or preco <= 0:
            return {"error": "Preço da ação deve ser maior que zero."}
        try:
            res_venda = sell_asset(ticker=ticker, quantidade=quantidade, preco=preco, notas=notas)
            summary = get_portfolio_summary()
            return {
                "status": "sucesso",
                "mensagem": f"Venda de {quantidade} {ticker.upper()} a R$ {preco:.2f} registrada!",
                "resultado_venda": res_venda,
                "resumo_carteira": {
                    "patrimonio_total": summary["patrimonio_total"],
                    "pl_total_pct": summary["pl_total_pct"],
                },
            }
        except ValueError as err:
            return {"error": str(err)}

    elif acao in ("posicao", "ativo", "detalhe"):
        if not ticker:
            return {"error": "Informe o ticker para consultar a posição."}
        pos_detalhe = get_position(ticker)
        if not pos_detalhe:
            return {"mensagem": f"Você não possui posição em custódia para {ticker.upper()}."}
        return {"posicao": pos_detalhe}

    elif acao in ("historico", "trades", "operacoes"):
        trades = load_trade_history()
        return {
            "total_trades": len(trades),
            "trades": trades[-15:],  # últimos 15
        }

    else:  # 'resumo', 'carteira', 'listar', 'status'
        summary = get_portfolio_summary()
        return summary
