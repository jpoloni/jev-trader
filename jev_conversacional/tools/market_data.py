"""get_market_data — FunctionTool ADK para cotação/candles determinísticos (yfinance)."""
from __future__ import annotations
from typing import Any
import logging
import os
import time

# Silencia o ruído do yfinance (HTTP 404, curl errors) pelo logger dele.
# Não usar contextlib.redirect_stdout/stderr: troca sys.stdout/stderr do processo inteiro
# e, com o scanner em threads, pode deixá-los apontando para um buffer descartado.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# cache simples 15 min (apenas dados reais ou simulados explicitamente; falhas não são cacheadas)
_CACHE: dict[str, tuple[float, dict]] = {}
TTL = 15 * 60

# Dados simulados só quando pedidos explicitamente (demos/testes offline).
MOCK_ENV_VAR = "JEV_MARKET_MOCK"


def _mock_enabled() -> bool:
    return os.getenv(MOCK_ENV_VAR, "").strip().lower() in ("1", "true", "yes", "sim")


def get_market_data(ticker: str) -> dict[str, Any]:
    """Retorna {preco_atual, variacao_dia_pct, candles_14d, indicadores, fundamentos, disponivel, fonte}.

    Sem API key. Usa yfinance. Se a cotação não puder ser obtida, retorna
    `disponivel=False` e `preco_atual=None` — nunca um preço inventado.
    Dados simulados só são usados com JEV_MARKET_MOCK=1 e vêm marcados com `simulado=True`.
    """
    key = ticker.upper().strip()
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < TTL:
        return _CACHE[key][1]

    if _mock_enabled():
        data = _mock_market_data(key)
        _CACHE[key] = (now, data)
        return data

    try:
        import yfinance as yf
        import pandas as pd
        # B3 tickers precisam .SA
        symbol = key if key.endswith(".SA") else f"{key}.SA"
        ticker_obj = yf.Ticker(symbol)
        hist = ticker_obj.history(period="3mo", interval="1d", auto_adjust=True)

        if hist.empty or len(hist) < 5:
            raise ValueError(f"histórico vazio ou insuficiente para {symbol}")

        closes = hist["Close"].dropna()
        highs = hist["High"].dropna() if "High" in hist else closes
        lows = hist["Low"].dropna() if "Low" in hist else closes
        volumes = hist["Volume"].dropna() if "Volume" in hist else None

        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) > 1 else last
        var_pct = ((last - prev) / prev * 100) if prev else 0.0

        candles = [
            {"data": str(idx.date()), "fechamento": round(float(v), 2)}
            for idx, v in zip(hist.tail(14).index, hist.tail(14)["Close"])
        ]

        # RSI 14
        delta = closes.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-9)
        rsi = float(100 - (100 / (1 + rs))) if not pd.isna(rs) else 50.0

        # Volatilidade 20d
        vol = float(closes.pct_change().rolling(20).std().iloc[-1] * 100) if len(closes) >= 20 else 2.5
        if pd.isna(vol):
            vol = 2.5

        # Médias móveis 20 vs 50
        mm20 = closes.rolling(20).mean().iloc[-1] if len(closes) >= 20 else None
        mm50 = closes.rolling(50).mean().iloc[-1] if len(closes) >= 50 else None
        if mm20 and mm50:
            mm_desc = "mm20 acima mm50 (tendência altista)" if mm20 > mm50 else "mm20 abaixo mm50 (tendência baixista)"
        else:
            mm_desc = "tendência neutra"

        # MACD (12, 26, 9)
        exp12 = closes.ewm(span=12, adjust=False).mean()
        exp26 = closes.ewm(span=26, adjust=False).mean()
        macd_line = exp12 - exp26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist_macd = macd_line - signal_line
        last_macd = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0.0
        last_sig = float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else 0.0
        last_hist = float(hist_macd.iloc[-1]) if not pd.isna(hist_macd.iloc[-1]) else 0.0
        if last_macd > last_sig:
            macd_desc = "cruzamento altista (MACD > Sinal)" if len(hist_macd) > 1 and hist_macd.iloc[-2] <= 0 else "momentum comprador positivo"
        else:
            macd_desc = "cruzamento baixista (MACD < Sinal)" if len(hist_macd) > 1 and hist_macd.iloc[-2] >= 0 else "momentum vendedor negativo"

        # Bandas de Bollinger (20 períodos, 2 desvios)
        bb_mid = closes.rolling(20).mean().iloc[-1] if len(closes) >= 20 else last
        bb_std = closes.rolling(20).std().iloc[-1] if len(closes) >= 20 else 0.0
        bb_upper = float(bb_mid + 2 * bb_std) if not pd.isna(bb_std) else last * 1.05
        bb_lower = float(bb_mid - 2 * bb_std) if not pd.isna(bb_std) else last * 0.95
        bb_mid_val = float(bb_mid) if not pd.isna(bb_mid) else last
        if last >= bb_upper:
            bb_pos = "tocando/acima da banda superior (sobrecompra)"
        elif last <= bb_lower:
            bb_pos = "tocando/abaixo da banda inferior (sobrevenda)"
        else:
            bb_pos = "dentro das bandas de Bollinger"

        # Volume relativo (vs média 20d)
        vol_rel = 1.0
        if volumes is not None and len(volumes) >= 5:
            vol_mean_20 = float(volumes.tail(20).mean())
            last_vol = float(volumes.iloc[-1])
            if vol_mean_20 > 0:
                vol_rel = round(last_vol / vol_mean_20, 2)

        # ATR 14 (Average True Range)
        atr_14 = round(last * 0.02, 2)
        if len(closes) >= 15:
            prev_c = closes.shift(1)
            tr1 = highs - lows
            tr2 = (highs - prev_c).abs()
            tr3 = (lows - prev_c).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            val_atr = tr.rolling(14).mean().iloc[-1]
            if not pd.isna(val_atr):
                atr_14 = round(float(val_atr), 2)

        # Suporte e Resistência dos últimos 20 pregões
        sup_20 = round(float(lows.tail(20).min()), 2) if len(lows) >= 5 else round(last * 0.95, 2)
        res_20 = round(float(highs.tail(20).max()), 2) if len(highs) >= 5 else round(last * 1.05, 2)

        # Fundamentos reais via info
        fundamentos: dict[str, Any] = {}
        nome_empresa = key
        setor_empresa = "Não informado"
        try:
            info = ticker_obj.info or {}
            nome_empresa = info.get("longName") or info.get("shortName") or key
            setor_empresa = info.get("sector") or "Não informado"

            def _clean_num(val, round_digits=2, pct_mult=1.0):
                if val is None or pd.isna(val):
                    return None
                try:
                    return round(float(val) * pct_mult, round_digits)
                except (ValueError, TypeError):
                    return None

            pl = _clean_num(info.get("trailingPE"), 2)
            pvp = _clean_num(info.get("priceToBook"), 2)
            roe = _clean_num(info.get("returnOnEquity"), 2, 100.0)
            dy_raw = info.get("dividendYield")
            if dy_raw is not None and not pd.isna(dy_raw):
                dy_val = float(dy_raw)
                dy = round(dy_val if dy_val > 1.0 else dy_val * 100.0, 2)
            else:
                dy = None
            divida_pl = _clean_num(info.get("debtToEquity"), 2)
            margem_liq = _clean_num(info.get("profitMargins"), 2, 100.0)
            mcap = info.get("marketCap")
            ev_ebitda = _clean_num(info.get("enterpriseToEbitda"), 2)

            fundamentos = {
                "pl_trailing": pl,
                "pvp": pvp,
                "roe_pct": roe,
                "dividend_yield_pct": dy,
                "divida_pl": divida_pl,
                "margem_liquida_pct": margem_liq,
                "valor_mercado": mcap,
                "ev_ebitda": ev_ebitda,
            }
            fundamentos = {k: v for k, v in fundamentos.items() if v is not None}
        except Exception:
            fundamentos = {}

        # Notícias recentes do Yahoo Finance
        noticias_recentes: list[str] = []
        try:
            raw_news = ticker_obj.news or []
            for n in raw_news[:5]:
                title = n.get("title")
                if not title and isinstance(n.get("content"), dict):
                    title = n.get("content", {}).get("title")
                provider = n.get("provider", {})
                pname = provider.get("displayName") if isinstance(provider, dict) else None
                if title:
                    noticias_recentes.append(f"{title} ({pname})" if pname else title)
        except Exception:
            noticias_recentes = []

        data: dict[str, Any] = {
            "ticker": key,
            "nome": nome_empresa,
            "setor": setor_empresa,
            "preco_atual": round(last, 2),
            "variacao_dia_pct": round(var_pct, 2),
            "candles_14d": candles,
            "indicadores": {
                "rsi_14": round(rsi, 1),
                "volatilidade_20d_pct": round(vol, 2),
                "mm_20_vs_50": mm_desc,
                "macd": {
                    "macd": round(last_macd, 2),
                    "signal": round(last_sig, 2),
                    "hist": round(last_hist, 2),
                    "desc": macd_desc,
                },
                "bollinger": {
                    "lower": round(bb_lower, 2),
                    "middle": round(bb_mid_val, 2),
                    "upper": round(bb_upper, 2),
                    "posicao": bb_pos,
                },
                "volume_relativo_20d": vol_rel,
                "atr_14": atr_14,
                "suporte_20d": sup_20,
                "resistencia_20d": res_20,
            },
            "fundamentos": fundamentos,
            "noticias_recentes": noticias_recentes,
            "fonte": "yfinance",
            "disponivel": True,
            "simulado": False,
        }
    except Exception as e:
        # Sem cotação real: sinaliza indisponibilidade em vez de inventar valores.
        # Não cacheia, para tentar de novo na próxima chamada.
        return {
            "ticker": key,
            "nome": key,
            "setor": "Não informado",
            "preco_atual": None,
            "variacao_dia_pct": None,
            "candles_14d": [],
            "indicadores": {},
            "fundamentos": {},
            "noticias_recentes": [],
            "fonte": "indisponivel",
            "disponivel": False,
            "simulado": False,
            "erro": f"cotação indisponível (yfinance): {e}",
        }

    _CACHE[key] = (now, data)
    return data


def _mock_market_data(key: str) -> dict[str, Any]:
    """Dados de mercado SIMULADOS (fixos) — só para demos/testes offline via JEV_MARKET_MOCK=1."""
    return {
        "ticker": key,
        "nome": f"{key} S.A.",
        "setor": "Petróleo, Gás e Biocombustíveis" if "PETR" in key else "Setor B3",
        "preco_atual": 38.42,
        "variacao_dia_pct": -1.2,
        "candles_14d": [{"data": "2026-09-18", "fechamento": 38.0 + i * 0.2} for i in range(14)],
        "indicadores": {
            "rsi_14": 68.2,
            "volatilidade_20d_pct": 2.8,
            "mm_20_vs_50": "mm20 acima mm50 (tendência altista)",
            "macd": {"macd": 1.12, "signal": 0.95, "hist": 0.17, "desc": "momentum comprador positivo"},
            "bollinger": {"lower": 36.5, "middle": 38.2, "upper": 39.9, "posicao": "dentro das bandas de Bollinger"},
            "volume_relativo_20d": 1.15,
            "atr_14": 0.85,
            "suporte_20d": 36.5,
            "resistencia_20d": 40.2,
        },
        "fundamentos": {
            "pl_trailing": 5.2,
            "pvp": 1.15,
            "roe_pct": 22.5,
            "dividend_yield_pct": 8.5,
            "margem_liquida_pct": 21.0,
        },
        "noticias_recentes": [f"Resultados operacionais e dividendos de {key}"],
        "fonte": "mock (dados simulados — JEV_MARKET_MOCK=1)",
        "disponivel": True,
        "simulado": True,
    }
