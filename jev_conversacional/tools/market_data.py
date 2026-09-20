"""get_market_data — FunctionTool ADK para cotação/candles determinísticos (yfinance)."""
from __future__ import annotations
from typing import Any
import time

# cache simples 15 min
_CACHE: dict[str, tuple[float, dict]] = {}
TTL = 15 * 60

def get_market_data(ticker: str) -> dict[str, Any]:
    """Retorna {preco_atual, variacao_dia_pct, candles_14d, indicadores: {rsi_14, volatilidade_20d_pct}}.

    Sem API key. Usa yfinance; fallback mock se offline.
    """
    key = ticker.upper().strip()
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < TTL:
        return _CACHE[key][1]

    try:
        import yfinance as yf
        import pandas as pd
        # B3 tickers precisam .SA
        symbol = key if key.endswith(".SA") else f"{key}.SA"
        hist = yf.Ticker(symbol).history(period="1mo", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 5:
            raise ValueError("hist empty")
        closes = hist["Close"].tolist()
        last = float(closes[-1])
        prev = float(closes[-2])
        var_pct = (last - prev) / prev * 100 if prev else 0.0
        candles = [
            {"data": str(idx.date()), "fechamento": round(float(v), 2)}
            for idx, v in zip(hist.tail(14).index, hist.tail(14)["Close"])
        ]
        # RSI 14 simples
        delta = hist["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-9)
        rsi = float(100 - (100 / (1 + rs))) if not pd.isna(rs) else 50.0
        vol = float(hist["Close"].pct_change().rolling(20).std().iloc[-1] * 100) if len(hist) >= 20 else 2.5

        data: dict[str, Any] = {
            "ticker": key,
            "preco_atual": round(last, 2),
            "variacao_dia_pct": round(var_pct, 2),
            "candles_14d": candles,
            "indicadores": {
                "rsi_14": round(rsi, 1),
                "volatilidade_20d_pct": round(vol, 2),
                "mm_20_vs_50": "não calculado (mock)",
            },
            "fonte": "yfinance",
        }
    except Exception as e:  # fallback mock para offline/testes
        data = {
            "ticker": key,
            "preco_atual": 38.42,
            "variacao_dia_pct": -1.2,
            "candles_14d": [{"data": "2026-09-18", "fechamento": 38.0 + i * 0.2} for i in range(14)],
            "indicadores": {"rsi_14": 68.2, "volatilidade_20d_pct": 2.8, "mm_20_vs_50": "mm20 acima mm50"},
            "fonte": f"mock (yfinance indisponível: {e})",
        }

    _CACHE[key] = (now, data)
    return data
