"""CLI Interativo e Elegante para o Jev Conversacional.

Interface de terminal moderna, sem ruído de logs/warnings experimentais, com
renderização formatada de markdown, spinner interativo e histórico persistente.
"""
from __future__ import annotations

import os
import sys
import time
import asyncio
import logging
import warnings
import threading
from typing import AsyncGenerator

# Silencia ruídos de dependências e logs de desenvolvimento antes de inicializar
warnings.filterwarnings("ignore")
for logger_name in ["google.adk", "google.genai", "opentelemetry", "urllib3", "yfinance"]:
    logging.getLogger(logger_name).setLevel(logging.ERROR)

class _FilteredStderr:
    def __init__(self, orig):
        self._orig = orig
    def write(self, s: str):
        if any(msg in s for msg in ["AFC is disabled", "automatic function calling", "EXPERIMENTAL", "InMemoryCredentialService"]):
            return len(s)
        return self._orig.write(s)
    def flush(self):
        self._orig.flush()
    def __getattr__(self, name):
        return getattr(self._orig, name)

sys.stderr = _FilteredStderr(sys.stderr)


from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.genai.types import Content, Part

from jev_conversacional.agent import root_agent
from jev_trader.cli_ui import Ansi, print_banner, badge_rec, USE_COLOR


class Spinner:
    """Spinner animado em thread para feedback visual sem travamento."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Consultando inteligência Jev..."):
        self.message = message
        self.running = False
        self._thread: threading.Thread | None = None

    def _spin(self):
        idx = 0
        while self.running:
            frame = self.FRAMES[idx % len(self.FRAMES)]
            if sys.stdout.isatty():
                sys.stdout.write(f"\r  {Ansi.BOLD}{Ansi.BRIGHT_CYAN}{frame}{Ansi.RESET} {Ansi.GRAY}{self.message}{Ansi.RESET} ")
                sys.stdout.flush()
            time.sleep(0.08)
            idx += 1
        if sys.stdout.isatty():
            # Limpa linha
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=0.5)


def render_terminal_markdown(text: str) -> str:
    """Renderizador leve de Markdown para terminal com cores ANSI e caixas visuais."""
    if not USE_COLOR:
        return text

    lines = text.split("\n")
    formatted_lines = []

    for line in lines:
        stripped = line.strip()

        # Cabeçalhos
        if stripped.startswith("### "):
            title = stripped[4:]
            formatted_lines.append(f"\n{Ansi.BOLD}{Ansi.BRIGHT_WHITE}▶ {title}{Ansi.RESET}")
        elif stripped.startswith("## "):
            title = stripped[3:]
            formatted_lines.append(f"\n{Ansi.BOLD}{Ansi.BRIGHT_CYAN}━━━ {title} ━━━{Ansi.RESET}")
        elif stripped.startswith("# "):
            title = stripped[2:]
            formatted_lines.append(f"\n{Ansi.BOLD}{Ansi.CYAN}═══ {title} ═══{Ansi.RESET}")

        # Citações / Callouts
        elif stripped.startswith("> "):
            callout = stripped[2:]
            # Alerta ou Gate
            if "⚠️" in callout or "Alerta" in callout or "Gate" in callout:
                formatted_lines.append(f"  {Ansi.BRIGHT_YELLOW}│{Ansi.RESET} {Ansi.BOLD}{Ansi.BRIGHT_YELLOW}{callout}{Ansi.RESET}")
            elif "⚖️" in callout or "Disclaimer" in callout or "CVM" in callout:
                formatted_lines.append(f"  {Ansi.GRAY}│ {callout}{Ansi.RESET}")
            else:
                formatted_lines.append(f"  {Ansi.CYAN}│{Ansi.RESET} {callout}")

        # Linhas de separação
        elif stripped in ("---", "___", "***"):
            formatted_lines.append(f"{Ansi.GRAY}{'─' * 70}{Ansi.RESET}")

        # Linhas de tabela (| ... |)
        elif stripped.startswith("|") and stripped.endswith("|"):
            if ":---" in stripped or "---:" in stripped or "---" in stripped:
                # Divisor de cabeçalho da tabela
                cols_count = stripped.count("|") - 1
                formatted_lines.append(f"  {Ansi.CYAN}{'─' * (cols_count * 16)}{Ansi.RESET}")
            else:
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                row_str = " │ ".join(cells)
                formatted_lines.append(f"  {Ansi.BOLD}│{Ansi.RESET} {row_str}")

        # Listas com marcadores
        elif stripped.startswith("- ") or stripped.startswith("* "):
            item = stripped[2:]
            formatted_lines.append(f"  • {item}")

        else:
            formatted_lines.append(line)

    res = "\n".join(formatted_lines)

    # Destaques inline
    res = res.replace("🟢 COMPRA", f"{Ansi.BOLD}{Ansi.BRIGHT_GREEN}🟢 COMPRA{Ansi.RESET}")
    res = res.replace("🟡 HOLD", f"{Ansi.BOLD}{Ansi.BRIGHT_YELLOW}🟡 HOLD{Ansi.RESET}")
    res = res.replace("🔴 VENDA", f"{Ansi.BOLD}{Ansi.BRIGHT_RED}🔴 VENDA{Ansi.RESET}")
    res = res.replace("✓ Aprovado", f"{Ansi.BRIGHT_GREEN}✓ Aprovado{Ansi.RESET}")

    return res


async def run_query(
    runner: Runner,
    session_id: str,
    user_query: str,
    user_id: str = "investidor_b3",
) -> str:
    """Envia query ao runner do agente e retorna o texto acumulado."""
    content = Content(role="user", parts=[Part.from_text(text=user_query)])
    parts_text = []

    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        if hasattr(event, "content") and event.content:
            for p in event.content.parts:
                if hasattr(p, "text") and p.text:
                    parts_text.append(p.text)

    response_text = "".join(parts_text)

    # Persiste no banco SQLite local
    try:
        from .sqlite_storage import save_message
        save_message(session_id, "user", user_query)
        save_message(session_id, "agent", response_text)
    except Exception:
        pass

    return response_text


def show_welcome_banner():
    width = 78
    print(f"\n{Ansi.BOLD}{Ansi.CYAN}┌{'─' * (width - 2)}┐{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}  {Ansi.BOLD}{Ansi.BRIGHT_WHITE}JEV CONVERSACIONAL{Ansi.RESET} — Assessor de Investimentos B3{' ' * 24}{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}  {Ansi.GRAY}Google ADK (Gemini 3.8 Flash) × Typesafe System One (jev-latest){' ' * 13}{Ansi.RESET}{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}├{'─' * (width - 2)}┤{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}  Exemplos:                                                                  {Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}    • {Ansi.BRIGHT_GREEN}\"Vale a pena comprar PETR4?\"{Ansi.RESET} ou {Ansi.BRIGHT_GREEN}\"Análise de VALE3 para swing\"{Ansi.RESET}{' ' * 15}{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}    • {Ansi.BRIGHT_YELLOW}\"Quais as melhores ações hoje?\"{Ansi.RESET} (Varredura B3 / scan_b3){' ' * 17}{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}    • {Ansi.BRIGHT_CYAN}\"Comprei 100 PETR4 a R$ 42,00\"{Ansi.RESET} ou {Ansi.BRIGHT_CYAN}\"Como está minha carteira?\"{Ansi.RESET}{' ' * 12}{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}  Comandos: {Ansi.BOLD}carteira{Ansi.RESET} │ {Ansi.BOLD}ranking{Ansi.RESET} (Top 10) │ {Ansi.BOLD}limpar{Ansi.RESET} │ {Ansi.BOLD}sair{Ansi.RESET}{' ' * 27}{Ansi.BOLD}{Ansi.CYAN}│{Ansi.RESET}")
    print(f"{Ansi.BOLD}{Ansi.CYAN}└{'─' * (width - 2)}┘{Ansi.RESET}\n")


async def async_main():
    # Inicializa serviços ADK em memória
    session_service = InMemorySessionService()
    memory_service = InMemoryMemoryService()
    app_name = "jev_conversacional_app"
    user_id = "investidor_local"
    session_counter = 1
    current_session_id = f"sessao_{session_counter}"

    await session_service.create_session(app_name=app_name, user_id=user_id, session_id=current_session_id)
    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        memory_service=memory_service,
    )

    # Modo 1: Execução de query única via linha de comando
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:]).strip()
        spinner = Spinner(f"Consultando Jev sobre: \"{query}\"...")
        spinner.start()
        try:
            resp = await run_query(runner, current_session_id, query, user_id=user_id)
        finally:
            spinner.stop()

        print(f"\n{Ansi.BOLD}{Ansi.CYAN}🤖 JEV:{Ansi.RESET}")
        print(render_terminal_markdown(resp))
        print()
        return

    # Modo 2: Chat Interativo
    show_welcome_banner()

    while True:
        try:
            prompt_str = f"{Ansi.BOLD}{Ansi.BRIGHT_CYAN}❯ {Ansi.BRIGHT_WHITE}[investidor]: {Ansi.RESET}"
            user_input = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Ansi.GRAY}Sessão encerrada. Até logo!{Ansi.RESET}\n")
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ("sair", "exit", "quit", "q"):
            print(f"\n{Ansi.GRAY}Sessão encerrada. Bons investimentos!{Ansi.RESET}\n")
            break
        elif cmd in ("limpar", "clear", "reset"):
            session_counter += 1
            current_session_id = f"sessao_{session_counter}"
            await session_service.create_session(app_name=app_name, user_id=user_id, session_id=current_session_id)
            print(f"\n{Ansi.BRIGHT_GREEN}✓ Nova sessão iniciada. Histórico anterior reiniciado.{Ansi.RESET}\n")
            continue
        elif cmd in ("ajuda", "help", "?"):
            show_welcome_banner()
            continue
        elif cmd in ("ranking", "top", "top10", "varredura"):
            user_input = "Quais as 10 melhores ações para swing hoje na B3? Varra o mercado."
        elif cmd in ("carteira", "portfolio", "pnl", "saldo", "custodia"):
            user_input = "Mostre o resumo consolidado da minha carteira de investimentos e P&L."

        spinner = Spinner("Consultando dados de mercado, notícias e inteligência Jev...")
        spinner.start()
        start_t = time.time()
        try:
            response_text = await run_query(runner, current_session_id, user_input, user_id=user_id)
        except Exception as e:
            response_text = f"Ocorreu um erro ao processar sua consulta: {e}"
        finally:
            spinner.stop()

        elapsed = time.time() - start_t
        print(f"\n{Ansi.BOLD}{Ansi.CYAN}🤖 JEV {Ansi.GRAY}({elapsed:.1f}s):{Ansi.RESET}")
        print(render_terminal_markdown(response_text))
        print(f"\n{Ansi.GRAY}{'─' * 70}{Ansi.RESET}\n")


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nSaindo...")
        sys.exit(0)


if __name__ == "__main__":
    main()
