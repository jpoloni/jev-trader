"""Universe B3 — carrega lista oficial de tickers com fallback determinístico."""
from __future__ import annotations

import json
import pathlib
import re
import urllib.request
import urllib.error

TICKER_RE = re.compile(r"^[A-Z]{4}\d{1,2}$")

# Snapshot Ibovespa vigente (~85, fallback canônico) — B3 carteira 2025/2026 (86 em jan/2025, 85 vigente)
# Ajustado em 2026-09-20: removido AZUL4 (RJ/delist Yahoo 404), adicionados B3SA3/BPAC11/BRKM5/CBAV3/CEAB3/CMIN3/CPLE6/CRFB3/ENAT3
IBOV_87 = [
    "ABEV3", "ALPA4", "ALOS3", "AMOB3", "ASAI3", "AURE3", "AZZA3", "B3SA3", "BBAS3", "BBDC3",
    "BBDC4", "BBSE3", "BEEF3", "BHIA3", "BPAC11", "BRAV3", "BRAP4", "BRFS3", "BRKM5", "CBAV3",
    "CEAB3", "CMIG4", "CMIN3", "COGN3", "CPLE3", "CPLE6", "CRFB3", "CSAN3", "CSNA3", "CXSE3",
    "CYRE3", "DIRR3", "EGIE3", "ELET3", "ELET6", "EMBR3", "ENAT3", "ENEV3", "ENGI11", "EQTL3",
    "EZTC3", "FLRY3", "GGBR4", "GOAU4", "HAPV3", "HYPE3", "IGTI11", "IRBR3", "ISAE4", "ITSA4",
    "ITUB4", "JBSS3", "KLBN11", "LREN3", "MGLU3", "MRFG3", "MRVE3", "MULT3", "NTCO3", "PETR3",
    "PETR4", "PETZ3", "POMO4", "PRIO3", "RAIL3", "RADL3", "RAIZ4", "RDOR3", "RECV3", "RENT3",
    "SANB11", "SBSP3", "SMFT3", "SMTO3", "SUZB3", "TAEE11", "TIMS3", "TOTS3", "UGPA3", "USIM5",
    "VALE3", "VBBR3", "VIVA3", "WEGE3", "YDUQ3",
]

# Lista curada ~250 líquidos (fallback expandido quando B3 fora do ar)
CURATED_250 = sorted(set(IBOV_87 + [
    "AESB3", "ALUP11", "AMAR3", "ANIM3", "ARZZ3", "BRSR6", "CASH3", "CCRO3",
    "CIEL3", "CPFE3", "CVCB3", "ECOR3", "ELMD3", "EQPA3", "EVEN3",
    "GGPS3", "GOLL4", "GRND3", "HBSA3", "HBOR3", "INTB3", "JHSF3", "KEPL3", "LEVE3", "LJQQ3",
    "LOGN3", "LWSA3", "MDIA3", "MILS3", "MOVI3", "ODPV3", "OIBR3", "PCAR3", "PDGR3", "PLPL3",
    "PSSA3", "QUAL3", "RANI3", "RAPT4", "ROMI3", "SAPR11", "SEER3", "SIMH3", "SLCE3", "STBP3",
]))

# clean placeholder (em caso de encoding)
CURATED_250 = [t for t in CURATED_250 if TICKER_RE.match(t)]

DEFAULT_CACHE = pathlib.Path(__file__).with_name("..") / "data" / "universe.json"
ALLOWLIST = {"PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "WEGE3"}

B3_API_URL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedCash"

def _fetch_b3_tickers(timeout: float = 6.0) -> list[str] | None:
    """Tenta buscar tickers da B3; retorna None se falhar."""
    try:
        req = urllib.request.Request(B3_API_URL, headers={"User-Agent": "jev-scanner/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            # Formato varia: pode ser lista de dicts com 'code' ou string
            tickers: list[str] = []
            # Alguns endpoints retornam {"results": [...]}
            candidates = data.get("results") if isinstance(data, dict) and "results" in data else data
            if isinstance(candidates, list):
                for item in candidates:
                    if isinstance(item, str) and TICKER_RE.match(item.strip().upper()):
                        tickers.append(item.strip().upper())
                    elif isinstance(item, dict):
                        for k in ("code", "ticker", "symbol", "codneg", "tradingName"):
                            v = item.get(k)
                            if isinstance(v, str) and TICKER_RE.match(v.strip().upper().split(".")[0].split(" ")[0]):
                                tickers.append(v.strip().upper().split(".")[0].split(" ")[0])
                                break
            tickers = sorted(set(t for t in tickers if TICKER_RE.match(t)))
            return tickers if tickers else None
    except Exception:
        return None

def load_universe(
    source: str = "b3",
    cache_path: str | pathlib.Path | None = None,
    fallback: str = "ibov",
    allow_network: bool = True,
) -> list[str]:
    """
    Carrega universo B3.

    Args:
        source: "b3" (tenta API), "ibov", "curated", "mock10", "file"
        cache_path: caminho para cache JSON (se existir, usado como fallback)
        fallback: "ibov" ou "curated" quando B3 falhar
        allow_network: se False, não tenta rede (útil para testes)
    Returns:
        Lista ordenada de tickers únicos.
    """
    source = source.lower()
    if source == "mock10":
        return ["PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "WEGE3", "MGLU3", "GGBR4", "USIM5", "LREN3"]
    if source == "ibov":
        return sorted(IBOV_87)
    if source == "curated":
        return sorted(CURATED_250)
    if source == "file" and cache_path:
        p = pathlib.Path(cache_path)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return sorted(set(t.strip().upper() for t in data if TICKER_RE.match(t.strip().upper())))
            except Exception:
                pass

    # source == "b3" (default)
    if allow_network:
        tickers = _fetch_b3_tickers()
        if tickers and len(tickers) >= 20:  # sanity: B3 deve ter >20
            # opcionalmente persiste cache
            if cache_path:
                try:
                    pathlib.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
                    pathlib.Path(cache_path).write_text(json.dumps(tickers, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            return tickers

    # fallback
    if cache_path:
        p = pathlib.Path(cache_path)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return sorted(set(t.strip().upper() for t in data if TICKER_RE.match(t.strip().upper())))
            except Exception:
                pass

    if fallback == "curated":
        return sorted(CURATED_250)
    return sorted(IBOV_87)
