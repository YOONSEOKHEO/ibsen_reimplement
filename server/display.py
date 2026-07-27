"""
Lightweight terminal presentation helpers for IBSEN.

Purpose: keep the play output readable by (1) silencing the verbose
initialization/debug noise and (2) formatting dialogue with per-speaker
colors, indentation and wrapping. Set the env var IBSEN_DEBUG=1 to restore
the original verbose behaviour (nothing is suppressed).
"""
import os
import sys
import textwrap
from contextlib import contextmanager

DEBUG = bool(os.environ.get("IBSEN_DEBUG"))

# --- ANSI styles ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"
GRAY = "\033[90m"

WIDTH = 88

# Colors are handed out to speakers in first-seen order so each character
# keeps a stable color throughout the play.
_SPEAKER_COLORS = [CYAN, YELLOW, GREEN, MAGENTA, BLUE, RED]
_assigned = {}


def color_for(name: str) -> str:
    if name not in _assigned:
        _assigned[name] = _SPEAKER_COLORS[len(_assigned) % len(_SPEAKER_COLORS)]
    return _assigned[name]


def _wrap(text: str, indent: str = "") -> str:
    out = []
    for para in str(text).split("\n"):
        out.append(textwrap.fill(
            para, width=WIDTH, initial_indent=indent, subsequent_indent=indent
        ) or indent)
    return "\n".join(out)


def format_dialogue(role: str, content: str) -> str:
    """Return a styled block for one line of the play."""
    content = str(content).strip()
    if role == "Narration":
        return f"{GRAY}{ITALIC}{_wrap('（' + content + '）', indent='   ')}{RESET}"
    header = f"{BOLD}{color_for(role)}{role}{RESET}"
    return f"{header}\n{_wrap(content, indent='   ')}"


def banner(title: str, subtitle: str = "") -> str:
    line = "=" * WIDTH
    out = f"\n{BOLD}{line}{RESET}\n{BOLD}  {title}{RESET}\n"
    if subtitle:
        out += f"{DIM}{_wrap(subtitle, indent='  ')}{RESET}\n"
    out += f"{BOLD}{line}{RESET}"
    return out


def rule(label: str = "") -> str:
    if label:
        pad = max(0, (WIDTH - len(label) - 2) // 2)
        return f"{DIM}{'-' * pad} {label} {'-' * pad}{RESET}"
    return f"{DIM}{'-' * WIDTH}{RESET}"


@contextmanager
def suppress_stdout():
    """Silence stdout during noisy blocks (e.g. stage init).

    stderr is left intact so genuine errors and tracebacks still surface.
    A no-op when IBSEN_DEBUG is set.
    """
    if DEBUG:
        yield
        return
    devnull = open(os.devnull, "w")
    old = sys.stdout
    sys.stdout = devnull
    try:
        yield
    finally:
        sys.stdout = old
        devnull.close()
