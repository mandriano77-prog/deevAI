"""Operational CLI — post-mortem job and future cron hooks."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .db import session_scope
from .services.meta_agent.post_mortem import run_due_post_mortems


async def _cmd_post_mortem() -> int:
    async with session_scope() as db:
        count = await run_due_post_mortems(db)
    print(f"Post-mortems processed: {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deevai_api")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("post-mortem", help="Run due agent post-mortems (alias)")
    sub.add_parser("run-post-mortems", help="Run due agent post-mortems")
    args = parser.parse_args(argv)

    if args.command in ("post-mortem", "run-post-mortems"):
        return asyncio.run(_cmd_post_mortem())
    return 1


if __name__ == "__main__":
    sys.exit(main())
