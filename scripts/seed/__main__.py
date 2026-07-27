"""CLI entrypoint: `python -m scripts.seed`."""

from __future__ import annotations

import argparse
import asyncio

from .runner import SeedRunner


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed",
        description="Seed SmartIDS backend database with deterministic local/demo data.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete seed-owned rows before reseeding.",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip post-seed service/auth validation.",
    )
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    runner = SeedRunner()
    report = await runner.run(reset=args.reset, validate=not args.skip_validate)

    print("")
    print("Seed summary:")
    for name, counts in report.entities.items():
        print(
            f"  {name}: created={counts.created} reused={counts.reused} deleted={counts.deleted} skipped={counts.skipped}"
        )

    print("")
    print("Demo accounts:")
    for credential in report.demo_credentials:
        password = credential.password or "<oauth-only>"
        print(f"  {credential.email} | password={password} | {credential.notes}")

    print("")
    print("Excluded tables:")
    for table_name, reason in report.excluded_tables:
        print(f"  {table_name}: {reason}")

    print("")
    print("Assumptions:")
    for item in report.assumptions:
        print(f"  - {item}")

    if report.validation_notes:
        print("")
        print("Validation:")
        for item in report.validation_notes:
            print(f"  - {item}")

    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
