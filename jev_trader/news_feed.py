"""Módulo de feed de notícias para ativos B3 (RSS Google News + Yahoo Finance)."""
from __future__ import annotations
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

# Cache simples em memória com TTL de 30 minutos
_NEWS_CACHE: dict[str, tuple[float, list[str]]] = {}
NEWS_TTL = 30 * 60  # 30 minutos


def get_news_feed(ticker: str, limit: int = 5) -> list[str]:
    """Retorna manchetes recentes para o ticker dado.
    
    1. Verifica cache em memória (TTL 30 min)
    2. Tenta buscar via Google News RSS (em português, focado em B3)
    3. Fallback para yfinance news
    4. Fallback descritivo seguro em caso de indisponibilidade
    """
    key = ticker.upper().strip()
    now = time.time()

    if key in _NEWS_CACHE and (now - _NEWS_CACHE[key][0]) < NEWS_TTL:
        return _NEWS_CACHE[key][1][:limit]

    headlines: list[str] = []

    # 1. Google News RSS em Português
    try:
        query = f"{key}+acao+OR+b3"
        url = f"https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            tree = ET.fromstring(response.read())
            items = tree.findall("./channel/item")
            for item in items[:limit]:
                title_elem = item.find("title")
                if title_elem is not None and title_elem.text:
                    title = title_elem.text.strip()
                    # Limpeza simples
                    if title and title not in headlines:
                        headlines.append(title)
    except Exception:
        headlines = []

    # 2. Fallback para Yahoo Finance se RSS falhar ou trouxer pouco
    if len(headlines) < 2:
        try:
            import yfinance as yf
            symbol = key if key.endswith(".SA") else f"{key}.SA"
            t = yf.Ticker(symbol)
            for n in (t.news or [])[:limit]:
                title = n.get("title")
                if not title and isinstance(n.get("content"), dict):
                    title = n.get("content", {}).get("title")
                provider = n.get("provider", {})
                pname = provider.get("displayName") if isinstance(provider, dict) else None
                if title:
                    entry = f"{title} ({pname})" if pname else title
                    if entry not in headlines:
                        headlines.append(entry)
        except Exception:
            pass

    if not headlines:
        headlines = [f"Acompanhamento de fluxo e oscilação de mercado para {key}"]

    _NEWS_CACHE[key] = (now, headlines)
    return headlines[:limit]
