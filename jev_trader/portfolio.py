"""Módulo de Gestão de Carteira Pessoal do Investidor Jev.

Persiste posições em data/portfolio.json e histórico de trades em data/trade_history.json.
Calcula preço médio ponderado, P&L não realizado e realizado, e exposição setorial.
"""
from __future__ import annotations

import json
import pathlib
import datetime
from typing import Any

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
TRADES_FILE = DATA_DIR / "trade_history.json"


def _load_json(file_path: pathlib.Path, default: Any) -> Any:
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(file_path: pathlib.Path, data: Any) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_portfolio() -> dict[str, dict[str, Any]]:
    """Carrega posições ativas da carteira {ticker: {quantidade, preco_medio, data_inicio}}."""
    return _load_json(PORTFOLIO_FILE, {})


def load_trade_history() -> list[dict[str, Any]]:
    """Carrega histórico de compras e vendas."""
    return _load_json(TRADES_FILE, [])


def buy_asset(
    ticker: str,
    quantidade: int,
    preco: float,
    data: str | None = None,
    notas: str | None = None,
) -> dict[str, Any]:
    """Registra compra de ações, calculando o novo preço médio ponderado."""
    ticker = ticker.upper().strip()
    if quantidade <= 0:
        raise ValueError("Quantidade deve ser positiva")
    if preco <= 0:
        raise ValueError("Preço deve ser positivo")

    hoje = data or datetime.date.today().isoformat()
    portfolio = load_portfolio()

    pos = portfolio.get(ticker)
    if pos:
        qtd_atual = int(pos.get("quantidade", 0))
        pm_atual = float(pos.get("preco_medio", 0.0))
        nova_qtd = qtd_atual + quantidade
        novo_pm = ((qtd_atual * pm_atual) + (quantidade * preco)) / nova_qtd
        portfolio[ticker] = {
            "ticker": ticker,
            "quantidade": nova_qtd,
            "preco_medio": round(novo_pm, 2),
            "data_inicio": pos.get("data_inicio", hoje),
            "ultima_atualizacao": hoje,
            "notas": notas or pos.get("notas", ""),
        }
    else:
        portfolio[ticker] = {
            "ticker": ticker,
            "quantidade": quantidade,
            "preco_medio": round(preco, 2),
            "data_inicio": hoje,
            "ultima_atualizacao": hoje,
            "notas": notas or "",
        }

    _save_json(PORTFOLIO_FILE, portfolio)

    # Registra trade
    trades = load_trade_history()
    trades.append({
        "tipo": "COMPRA",
        "ticker": ticker,
        "quantidade": quantidade,
        "preco": round(preco, 2),
        "data": hoje,
        "notas": notas or "",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    _save_json(TRADES_FILE, trades)

    return portfolio[ticker]


def sell_asset(
    ticker: str,
    quantidade: int,
    preco: float,
    data: str | None = None,
    notas: str | None = None,
) -> dict[str, Any]:
    """Registra venda parcial ou total de ações, apurando o lucro/prejuízo realizado."""
    ticker = ticker.upper().strip()
    if quantidade <= 0:
        raise ValueError("Quantidade deve ser positiva")
    if preco <= 0:
        raise ValueError("Preço deve ser positivo")

    portfolio = load_portfolio()
    pos = portfolio.get(ticker)
    if not pos:
        raise ValueError(f"Você não possui posição ativa em {ticker} para vender.")

    qtd_atual = int(pos.get("quantidade", 0))
    if quantidade > qtd_atual:
        raise ValueError(
            f"Quantidade de venda ({quantidade}) maior que a custódia atual de {ticker} ({qtd_atual})."
        )

    pm = float(pos.get("preco_medio", 0.0))
    pl_realizado_reais = round((preco - pm) * quantidade, 2)
    pl_realizado_pct = round(((preco - pm) / pm) * 100, 2) if pm > 0 else 0.0
    hoje = data or datetime.date.today().isoformat()

    restante = qtd_atual - quantidade
    if restante == 0:
        del portfolio[ticker]
    else:
        portfolio[ticker]["quantidade"] = restante
        portfolio[ticker]["ultima_atualizacao"] = hoje

    _save_json(PORTFOLIO_FILE, portfolio)

    # Registra trade
    trades = load_trade_history()
    trade_record = {
        "tipo": "VENDA",
        "ticker": ticker,
        "quantidade": quantidade,
        "preco_venda": round(preco, 2),
        "preco_medio_custo": pm,
        "pl_realizado_reais": pl_realizado_reais,
        "pl_realizado_pct": pl_realizado_pct,
        "data": hoje,
        "notas": notas or "",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    trades.append(trade_record)
    _save_json(TRADES_FILE, trades)

    return {
        "ticker": ticker,
        "quantidade_vendida": quantidade,
        "quantidade_restante": restante,
        "preco_venda": round(preco, 2),
        "preco_medio": pm,
        "pl_realizado_reais": pl_realizado_reais,
        "pl_realizado_pct": pl_realizado_pct,
    }


def get_position(ticker: str) -> dict[str, Any] | None:
    """Retorna detalhes de uma posição com cotação atual e % da carteira."""
    ticker = ticker.upper().strip()
    portfolio = load_portfolio()
    pos = portfolio.get(ticker)
    if not pos:
        return None

    try:
        from jev_conversacional.tools.market_data import get_market_data
        md = get_market_data(ticker)
        preco_atual = float(md.get("preco_atual") or pos["preco_medio"])
        var_dia = float(md.get("variacao_dia_pct") or 0.0)
    except Exception:
        preco_atual = float(pos["preco_medio"])
        var_dia = 0.0

    qtd = int(pos["quantidade"])
    pm = float(pos["preco_medio"])
    valor_investido = round(pm * qtd, 2)
    valor_atual = round(preco_atual * qtd, 2)
    pl_reais = round(valor_atual - valor_investido, 2)
    pl_pct = round(((preco_atual - pm) / pm * 100), 2) if pm > 0 else 0.0

    # Calcula patrimônio total da carteira para alocação percentual
    total_patrimonio = 0.0
    for t_code, p_data in portfolio.items():
        if t_code == ticker:
            total_patrimonio += valor_atual
        else:
            try:
                from jev_conversacional.tools.market_data import get_market_data
                other_md = get_market_data(t_code)
                p_cur = float(other_md.get("preco_atual") or p_data["preco_medio"])
            except Exception:
                p_cur = float(p_data["preco_medio"])
            total_patrimonio += p_cur * int(p_data["quantidade"])

    pct_carteira = round((valor_atual / total_patrimonio * 100), 1) if total_patrimonio > 0 else 0.0

    return {
        "ticker": ticker,
        "quantidade": qtd,
        "preco_medio": pm,
        "preco_atual": round(preco_atual, 2),
        "variacao_dia_pct": round(var_dia, 2),
        "valor_investido": valor_investido,
        "valor_atual": valor_atual,
        "pl_reais": pl_reais,
        "pl_pct": pl_pct,
        "pct_carteira": pct_carteira,
        "data_inicio": pos.get("data_inicio"),
        "notas": pos.get("notas", ""),
    }


def get_portfolio_summary() -> dict[str, Any]:
    """Calcula relatório consolidado com cotações ao vivo, P&L e alocação setorial."""
    portfolio = load_portfolio()
    if not portfolio:
        return {
            "posicoes": [],
            "patrimonio_total": 0.0,
            "total_investido": 0.0,
            "pl_total_reais": 0.0,
            "pl_total_pct": 0.0,
            "exposicao_setorial": {},
            "total_ativos": 0,
        }

    itens = []
    total_investido = 0.0
    patrimonio_total = 0.0
    setores_map: dict[str, float] = {}

    for ticker, pos in portfolio.items():
        try:
            from jev_conversacional.tools.market_data import get_market_data
            md = get_market_data(ticker)
            preco_atual = float(md.get("preco_atual") or pos["preco_medio"])
            var_dia = float(md.get("variacao_dia_pct") or 0.0)
            setor = str(md.get("setor") or "Outros")
            nome = str(md.get("nome") or ticker)
        except Exception:
            preco_atual = float(pos["preco_medio"])
            var_dia = 0.0
            setor = "Outros"
            nome = ticker

        qtd = int(pos["quantidade"])
        pm = float(pos["preco_medio"])
        v_investido = round(pm * qtd, 2)
        v_atual = round(preco_atual * qtd, 2)
        pl_r = round(v_atual - v_investido, 2)
        pl_p = round(((preco_atual - pm) / pm * 100), 2) if pm > 0 else 0.0

        total_investido += v_investido
        patrimonio_total += v_atual
        setores_map[setor] = setores_map.get(setor, 0.0) + v_atual

        itens.append({
            "ticker": ticker,
            "nome": nome,
            "setor": setor,
            "quantidade": qtd,
            "preco_medio": pm,
            "preco_atual": round(preco_atual, 2),
            "variacao_dia_pct": round(var_dia, 2),
            "valor_investido": v_investido,
            "valor_atual": v_atual,
            "pl_reais": pl_r,
            "pl_pct": pl_p,
            "data_inicio": pos.get("data_inicio"),
        })

    # Calcula alocação percentual individual e setorial
    for item in itens:
        item["pct_carteira"] = round((item["valor_atual"] / patrimonio_total * 100), 1) if patrimonio_total > 0 else 0.0

    exposicao_setorial = {
        s: round((val / patrimonio_total * 100), 1)
        for s, val in sorted(setores_map.items(), key=lambda x: -x[1])
    } if patrimonio_total > 0 else {}

    pl_total_reais = round(patrimonio_total - total_investido, 2)
    pl_total_pct = round(((patrimonio_total - total_investido) / total_investido * 100), 2) if total_investido > 0 else 0.0

    # Ordena por valor atual decrescente
    itens.sort(key=lambda x: -x["valor_atual"])

    return {
        "posicoes": itens,
        "patrimonio_total": round(patrimonio_total, 2),
        "total_investido": round(total_investido, 2),
        "pl_total_reais": pl_total_reais,
        "pl_total_pct": pl_total_pct,
        "exposicao_setorial": exposicao_setorial,
        "total_ativos": len(itens),
    }


def clear_portfolio() -> None:
    """Zera a carteira (usado em testes ou reset)."""
    if PORTFOLIO_FILE.exists():
        PORTFOLIO_FILE.unlink()
