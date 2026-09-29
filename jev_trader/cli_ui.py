"""Utilitários de formatação e design para interfaces de linha de comando (CLI) do Jev.

Design moderno, profissional e limpo inspirado em ferramentas modernas (gh, uv, docker),
com suporte a cores ANSI, mini-barras de score, badges e compatibilidade com pipes/redirecionamento.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Sequence

def _should_use_color() -> bool:
    if os.getenv("NO_COLOR") or os.getenv("TERM") == "dumb":
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()

USE_COLOR = _should_use_color()

class Ansi:
    RESET = "\033[0m" if USE_COLOR else ""
    BOLD = "\033[1m" if USE_COLOR else ""
    DIM = "\033[2m" if USE_COLOR else ""
    ITALIC = "\033[3m" if USE_COLOR else ""
    UNDERLINE = "\033[4m" if USE_COLOR else ""

    # Foreground
    BLACK = "\033[30m" if USE_COLOR else ""
    RED = "\033[31m" if USE_COLOR else ""
    GREEN = "\033[32m" if USE_COLOR else ""
    YELLOW = "\033[33m" if USE_COLOR else ""
    BLUE = "\033[34m" if USE_COLOR else ""
    MAGENTA = "\033[35m" if USE_COLOR else ""
    CYAN = "\033[36m" if USE_COLOR else ""
    WHITE = "\033[37m" if USE_COLOR else ""
    GRAY = "\033[90m" if USE_COLOR else ""

    # High-intensity
    BRIGHT_GREEN = "\033[92m" if USE_COLOR else ""
    BRIGHT_YELLOW = "\033[93m" if USE_COLOR else ""
    BRIGHT_RED = "\033[91m" if USE_COLOR else ""
    BRIGHT_CYAN = "\033[96m" if USE_COLOR else ""
    BRIGHT_WHITE = "\033[97m" if USE_COLOR else ""


def set_color_enabled(enabled: bool) -> None:
    """Ativa ou desativa cores dinamicamente."""
    global USE_COLOR
    USE_COLOR = enabled
    for attr in dir(Ansi):
        if not attr.startswith("_"):
            if not enabled:
                setattr(Ansi, attr, "")


def badge_rec(rec: str) -> str:
    """Retorna badge visual colorido para a recomendação."""
    r = (rec or "").strip().lower()
    if r == "compra":
        return f"{Ansi.BOLD}{Ansi.BRIGHT_GREEN}🟢 COMPRA{Ansi.RESET}"
    elif r == "venda":
        return f"{Ansi.BOLD}{Ansi.BRIGHT_RED}🔴 VENDA {Ansi.RESET}"
    return f"{Ansi.BOLD}{Ansi.BRIGHT_YELLOW}🟡 HOLD  {Ansi.RESET}"


def make_bar(value: float, max_value: float = 4.0, length: int = 10, fill_char: str = "█", empty_char: str = "░") -> str:
    """Renderiza mini-barra gráfica colorida para scores."""
    if max_value <= 0:
        pct = 0.0
    else:
        pct = max(0.0, min(1.0, value / max_value))
    filled = int(round(pct * length))
    empty = length - filled

    if pct >= 0.70:
        c = Ansi.BRIGHT_GREEN
    elif pct >= 0.40:
        c = Ansi.BRIGHT_YELLOW
    else:
        c = Ansi.BRIGHT_RED

    return f"{c}{fill_char * filled}{Ansi.GRAY}{empty_char * empty}{Ansi.RESET}"


def format_currency(val: float | None) -> str:
    if val is None:
        return "R$ --"
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_pct(val: float | None) -> str:
    if val is None:
        return "--%"
    signal = "+" if val > 0 else ""
    color = Ansi.BRIGHT_GREEN if val > 0 else (Ansi.BRIGHT_RED if val < 0 else Ansi.GRAY)
    return f"{color}{signal}{val:.2f}%{Ansi.RESET}"


def print_banner(title: str, subtitle: str | None = None) -> None:
    """Exibe banner de cabeçalho formatado."""
    w = 78
    print(f"\n{Ansi.BOLD}{Ansi.CYAN}┌{'─' * (w - 2)}┐{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}{Ansi.BRIGHT_WHITE}{title}{Ansi.RESET}")
    if subtitle:
        print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}  {Ansi.GRAY}{subtitle}{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}└{'─' * (w - 2)}┘{Ansi.RESET}\n")


def render_ticker_card(result: dict[str, Any]) -> str:
    """Renderiza a análise completa de um ativo como um card visual detalhado."""
    ticker = result.get("ticker", "UNKNOWN")
    rec = result.get("recomendacao", "hold")
    weighted = float(result.get("weighted", 0.0))
    confidence = float(result.get("confidence", 0.0))
    probs = result.get("probabilidades", {})
    scores = result.get("scores", {})
    gates = result.get("gates", {})
    motivo_gate = result.get("motivo_gate")
    justificativa = result.get("justificativa", "")
    model = result.get("model", "jev")
    usage = result.get("usage", {})
    disclaimer = result.get("disclaimer", "Res. CVM 20")

    state = result.get("state", {})
    ativo = state.get("ativo", {})
    nome = ativo.get("nome", ticker)
    setor = ativo.get("setor", "B3")
    mercado = state.get("mercado", {})
    preco_atual = mercado.get("preco_atual")
    var_dia = mercado.get("variacao_dia_pct")

    p_compra = probs.get("compra", 0.0) * 100
    p_hold = probs.get("hold", 0.0) * 100
    p_venda = probs.get("venda", 0.0) * 100

    w = 74
    line_div = f"{Ansi.CYAN}├{'─' * (w - 2)}┤{Ansi.RESET}"

    out = []
    # Header
    out.append(f"{Ansi.BOLD}{Ansi.CYAN}┌─ JEV TRADER ── Análise de Ativo {('─' * (w - 35))}┐{Ansi.RESET}")
    info_sub = f"{ticker} · {nome}"
    if setor and setor != "Não informado":
        info_sub += f" · {setor}"
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}{Ansi.BRIGHT_WHITE}{info_sub}{Ansi.RESET}")
    if preco_atual is not None:
        out.append(f"{Ansi.CYAN}│{Ansi.RESET}  Cotação: {format_currency(preco_atual)} ({format_pct(var_dia)})")
    else:
        out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BRIGHT_YELLOW}⚠️  Cotação indisponível — análise sem dados de mercado reais{Ansi.RESET}")
    
    out.append(line_div)

    # Veredito
    weighted_bar = make_bar(weighted, max_value=1.0, length=8)
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}Recomendação:{Ansi.RESET}     {badge_rec(rec)}")
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}Score Ponderado:{Ansi.RESET}  {Ansi.BOLD}{weighted:.3f}{Ansi.RESET} {weighted_bar}  (Confiança: {Ansi.BOLD}{confidence*100:.1f}%{Ansi.RESET})")
    out.append(
        f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}Probabilidades:{Ansi.RESET}   "
        f"Compra: {Ansi.BRIGHT_GREEN}{p_compra:.1f}%{Ansi.RESET} │ "
        f"Hold: {Ansi.BRIGHT_YELLOW}{p_hold:.1f}%{Ansi.RESET} │ "
        f"Venda: {Ansi.BRIGHT_RED}{p_venda:.1f}%{Ansi.RESET}"
    )

    out.append(line_div)

    # Scores
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}{Ansi.WHITE}Scores Analíticos (0 a 4):{Ansi.RESET}")
    score_items = [
        ("Tendência Técnica", scores.get("tendencia_tecnica", 0.0), 4.0),
        ("Qualidade Fundamentalista", scores.get("qualidade_fundamentalista", 0.0), 4.0),
        ("Sentimento de Notícias", scores.get("sentimento_noticia", 0.0), 4.0),
        ("Timing / Momentum", scores.get("timing_momentum", 0.0), 4.0),
        ("Risco / Volatilidade", scores.get("risco_volatilidade", 0.0), 3.0),
    ]
    for label, val, max_v in score_items:
        bar = make_bar(val, max_value=max_v, length=10)
        note = " (menor é melhor)" if "Risco" in label else ""
        out.append(f"{Ansi.CYAN}│{Ansi.RESET}    • {label:28s} {bar}  {Ansi.BOLD}{val:3.1f}{Ansi.RESET} / {max_v:3.1f}{Ansi.GRAY}{note}{Ansi.RESET}")

    out.append(line_div)

    # Gates
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}{Ansi.WHITE}Gates de Segurança & Risco:{Ansi.RESET}")
    g_risco = gates.get("risco_excessivo", 0.0)
    g_info = gates.get("informacao_insuficiente", 0.0)
    g_event = gates.get("evento_binario_iminente", 0.0)

    def _g_status(v: float, lim: float) -> str:
        if v > lim:
            return f"{Ansi.BRIGHT_RED}❌ BLOQUEIO ({v:.2f} > limite {lim:.2f}){Ansi.RESET}"
        return f"{Ansi.BRIGHT_GREEN}✓ OK ({v:.2f} <= {lim:.2f}){Ansi.RESET}"

    out.append(f"{Ansi.CYAN}│{Ansi.RESET}    • Risco Excessivo:         {_g_status(g_risco, 0.70)}")
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}    • Informação Insuficiente: {_g_status(g_info, 0.68)}")
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}    • Evento Binário Iminente: {_g_status(g_event, 0.65)}")
    if motivo_gate:
        out.append(f"{Ansi.CYAN}│{Ansi.RESET}    {Ansi.BOLD}{Ansi.BRIGHT_YELLOW}⚠️  Ação Soberana:{Ansi.RESET} {motivo_gate}")
    else:
        out.append(f"{Ansi.CYAN}│{Ansi.RESET}    {Ansi.BRIGHT_GREEN}✓ Aprovado — nenhum bloqueio acionado.{Ansi.RESET}")

    out.append(line_div)

    # Justificativa
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}{Ansi.WHITE}Síntese da Decisão:{Ansi.RESET}")
    # Quebra de linha simples
    words = justificativa.split()
    cur = "    "
    for w_word in words:
        if len(cur) + len(w_word) + 1 > w - 4:
            out.append(f"{Ansi.CYAN}│{Ansi.RESET}{cur}")
            cur = "    " + w_word
        else:
            cur += (" " if cur.strip() else "") + w_word
    if cur.strip():
        out.append(f"{Ansi.CYAN}│{Ansi.RESET}{cur}")

    out.append(line_div)

    # Footer
    in_tok = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
    out_tok = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.GRAY}Modelo: {model} │ Tokens: {in_tok} in / {out_tok} out{Ansi.RESET}")
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.GRAY}⚠️  {disclaimer}{Ansi.RESET}")
    out.append(f"{Ansi.BOLD}{Ansi.CYAN}└{'─' * (w - 2)}┘{Ansi.RESET}")

    return "\n".join(out)


def render_ranking_table(results: Sequence[Any], top: int = 20, horizonte: str = "swing") -> str:
    """Renderiza tabela de ranking limpa e alinhada."""
    to_display = results[:top]
    if not to_display:
        return f"{Ansi.GRAY}(Nenhum resultado para exibir){Ansi.RESET}"

    # Header da tabela
    out = []
    sep = "─" * 90
    out.append(f"{Ansi.CYAN}{sep}{Ansi.RESET}")
    out.append(
        f"{Ansi.BOLD}{Ansi.WHITE}"
        f"{'Pos':>3}  "
        f"{'Ticker':<6}  "
        f"{'Recomendação':<13}  "
        f"{'Score Pond.':<14}  "
        f"{'Confiança':>6}   "
        f"{'Probabilidades':<18}  "
        f"{'Status Gate'}"
        f"{Ansi.RESET}"
    )
    out.append(f"{Ansi.CYAN}{sep}{Ansi.RESET}")

    for i, r in enumerate(to_display, 1):
        ticker = getattr(r, "ticker", "")
        rec = getattr(r, "recomendacao", "hold")
        weighted = float(getattr(r, "weighted", 0.0))
        conf = float(getattr(r, "confidence", 0.0))
        probs = getattr(r, "probabilidades", {}) or {}
        motivo_gate = getattr(r, "motivo_gate", None)

        badge = badge_rec(rec)
        score_bar = make_bar(weighted, max_value=1.0, length=6)
        score_num = f"{weighted:.3f}"
        conf_txt = f"{conf * 100:4.1f}%"

        pc = int(round(probs.get("compra", 0.0) * 100))
        ph = int(round(probs.get("hold", 0.0) * 100))
        pv = int(round(probs.get("venda", 0.0) * 100))
        probs_txt = (
            f"{Ansi.BRIGHT_GREEN}C:{pc:02d}%{Ansi.RESET} "
            f"{Ansi.BRIGHT_YELLOW}H:{ph:02d}%{Ansi.RESET} "
            f"{Ansi.BRIGHT_RED}V:{pv:02d}%{Ansi.RESET}"
        )

        if motivo_gate:
            gate_short = motivo_gate.replace("divergência", "diverg.").replace("informacao_insuficiente", "info_insuf")
            if len(gate_short) > 24:
                gate_short = gate_short[:21] + "..."
            gate_txt = f"{Ansi.BRIGHT_YELLOW}⚠️  {gate_short}{Ansi.RESET}"
        else:
            gate_txt = f"{Ansi.BRIGHT_GREEN}✓ Aprovado{Ansi.RESET}"

        row = (
            f"{i:>3}  "
            f"{Ansi.BOLD}{ticker:<6}{Ansi.RESET}  "
            f"{badge}    "
            f"{score_num} {score_bar}  "
            f"{conf_txt:>6}   "
            f"{probs_txt}  "
            f"{gate_txt}"
        )
        out.append(row)


    out.append(f"{Ansi.CYAN}{sep}{Ansi.RESET}")
    return "\n".join(out)



def render_scan_summary(
    results: Sequence[Any],
    paths: dict[str, str],
    universe_name: str,
    horizonte: str,
    duration_s: float | None = None,
) -> str:
    """Renderiza painel de resumo da varredura com contagens e links de arquivos."""
    total = len(results)
    if total == 0:
        return ""

    n_compra = sum(1 for r in results if getattr(r, "recomendacao", "") == "compra")
    n_hold = sum(1 for r in results if getattr(r, "recomendacao", "") == "hold")
    n_venda = sum(1 for r in results if getattr(r, "recomendacao", "") == "venda")
    n_gates = sum(1 for r in results if getattr(r, "motivo_gate", None))

    w = 76
    out = []
    out.append(f"\n{Ansi.BOLD}{Ansi.CYAN}┌─ RESUMO DA VARREDURA B3 {('─' * (w - 27))}┐{Ansi.RESET}")
    
    dur_txt = f" em {duration_s:.1f}s" if duration_s is not None else ""
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  Universo: {Ansi.BOLD}{universe_name}{Ansi.RESET} ({total} ativos varridos{dur_txt}) · Horizonte: {Ansi.BOLD}{horizonte}{Ansi.RESET}")
    out.append(
        f"{Ansi.CYAN}│{Ansi.RESET}  Distribuição: "
        f"{Ansi.BRIGHT_GREEN}🟢 {n_compra} Compra ({n_compra*100/total:.0f}%){Ansi.RESET} │ "
        f"{Ansi.BRIGHT_YELLOW}🟡 {n_hold} Hold ({n_hold*100/total:.0f}%){Ansi.RESET} │ "
        f"{Ansi.BRIGHT_RED}🔴 {n_venda} Venda ({n_venda*100/total:.0f}%){Ansi.RESET} │ "
        f"{Ansi.GRAY}Bloqueios: {n_gates}{Ansi.RESET}"
    )

    out.append(f"{Ansi.CYAN}├{'─' * (w - 2)}┤{Ansi.RESET}")
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}Arquivos gerados e atualizados:{Ansi.RESET}")
    for k, p in paths.items():
        tag = k.upper()
        out.append(f"{Ansi.CYAN}│{Ansi.RESET}    • [{Ansi.BRIGHT_CYAN}{tag:<6}{Ansi.RESET}] {p}")

    disclaimer = getattr(results[0], "disclaimer", "Res. CVM 20") if results else "Res. CVM 20"
    out.append(f"{Ansi.CYAN}├{'─' * (w - 2)}┤{Ansi.RESET}")
    out.append(f"{Ansi.CYAN}│{Ansi.RESET}  {Ansi.GRAY}⚠️  {disclaimer}{Ansi.RESET}")
    out.append(f"{Ansi.BOLD}{Ansi.CYAN}└{'─' * (w - 2)}┘{Ansi.RESET}\n")

    return "\n".join(out)


class ScanProgressBar:
    """Barra de progresso interativa para terminal em varreduras assíncronas."""

    def __init__(self, total: int, description: str = "Varrendo B3"):
        self.total = total
        self.description = description
        self.completed = 0
        self.current_ticker = ""
        self.is_tty = sys.stdout.isatty() and USE_COLOR

    def update(self, count: int = 1, current_ticker: str = "") -> None:
        self.completed += count
        if current_ticker:
            self.current_ticker = current_ticker
        self._render()

    def _render(self) -> None:
        if not self.is_tty:
            return
        pct = (self.completed / self.total) if self.total > 0 else 1.0
        bar_len = 22
        filled = int(round(pct * bar_len))
        empty = bar_len - filled

        bar = f"{Ansi.BRIGHT_GREEN}{'█' * filled}{Ansi.GRAY}{'░' * empty}{Ansi.RESET}"
        ticker_info = f"[{self.current_ticker:6s}]" if self.current_ticker else ""
        text = f"\r  {Ansi.BOLD}{Ansi.CYAN}{self.description}:{Ansi.RESET} [{bar}] {self.completed:2d}/{self.total} ({pct*100:4.1f}%) {Ansi.GRAY}{ticker_info}{Ansi.RESET}"
        sys.stdout.write(text)
        sys.stdout.flush()

    def finish(self) -> None:
        if self.is_tty:
            sys.stdout.write("\n")
            sys.stdout.flush()
