"""`bpx` console entry point."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bpx",
        description="british_pixelart_llm — Textual TUI chat over local LLMs.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "setup", help="Check Ollama and required models (Phase-0 stub; see PLAN.md §14)."
    )
    args = parser.parse_args()

    if args.command == "setup":
        from .setup import run_setup

        run_setup()
        return

    from .app import ChatApp

    ChatApp().run()
