"""CLI tool for empirical online-validation logs and markdown report generation.

Examples:
  python scripts/online_validation_tool.py add-matrix --pair-a Eden --pair-b Ryujinx --result FAIL
  python scripts/online_validation_tool.py add-rtt --mode Public --runs 5 --avg-rtt-ms 42.5
  python scripts/online_validation_tool.py render
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.online_validation import (
    add_matrix_run,
    add_rtt_run,
    load_data,
    matrix_coverage_summary,
    rtt_mode_summary,
    save_data,
    seed_default_matrix_entries,
    write_reports,
)

DATA_PATH = REPO_ROOT / "docs" / "online_validation_data.json"
MATRIX_RESULTS_PATH = REPO_ROOT / "docs" / "emulator_pair_matrix_results.md"
RTT_RESULTS_PATH = REPO_ROOT / "docs" / "public_unlisted_rtt_results.md"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Online empirical validation logger")
    sub = parser.add_subparsers(dest="command", required=True)

    add_matrix = sub.add_parser("add-matrix", help="Record emulator pair run")
    add_matrix.add_argument("--pair-a", required=True)
    add_matrix.add_argument("--pair-b", required=True)
    add_matrix.add_argument("--result", choices=["PASS", "FAIL", "UNVERIFIED"], required=True)
    add_matrix.add_argument("--build-a", default="")
    add_matrix.add_argument("--build-b", default="")
    add_matrix.add_argument("--notes", default="")
    add_matrix.add_argument("--date", default="")

    add_rtt = sub.add_parser("add-rtt", help="Record public/unlisted RTT run")
    add_rtt.add_argument("--mode", choices=["Public", "Unlisted"], required=True)
    add_rtt.add_argument("--runs", type=int, required=True)
    add_rtt.add_argument("--avg-rtt-ms", type=float, required=True)
    add_rtt.add_argument("--disconnects", type=int, default=0)
    add_rtt.add_argument("--host-build", default="")
    add_rtt.add_argument("--client-build", default="")
    add_rtt.add_argument("--notes", default="")
    add_rtt.add_argument("--date", default="")

    sub.add_parser("render", help="Regenerate markdown reports from current JSON data")
    sub.add_parser("status", help="Print current run counts")
    sub.add_parser("next", help="Print next recommended logging commands for pending evidence")
    sub.add_parser("seed-defaults", help="Seed canonical UNVERIFIED matrix entries")
    return parser


def _save_and_render(data: dict) -> None:
    save_data(DATA_PATH, data)
    write_reports(
        data=data,
        matrix_report_path=MATRIX_RESULTS_PATH,
        rtt_report_path=RTT_RESULTS_PATH,
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    data = load_data(DATA_PATH)

    if args.command == "add-matrix":
        add_matrix_run(
            data,
            pair_a=args.pair_a,
            pair_b=args.pair_b,
            result=args.result,
            build_a=args.build_a,
            build_b=args.build_b,
            notes=args.notes,
            run_date=args.date or None,
        )
        _save_and_render(data)
        print("Recorded matrix run and regenerated reports.")
        return 0

    if args.command == "add-rtt":
        add_rtt_run(
            data,
            mode=args.mode,
            runs=args.runs,
            avg_rtt_ms=args.avg_rtt_ms,
            disconnects=args.disconnects,
            host_build=args.host_build,
            client_build=args.client_build,
            notes=args.notes,
            run_date=args.date or None,
        )
        _save_and_render(data)
        print("Recorded RTT run and regenerated reports.")
        return 0

    if args.command == "render":
        _save_and_render(data)
        print("Rendered reports from existing validation data.")
        return 0

    if args.command == "status":
        matrix_count = len(data.get("matrix_runs", []))
        rtt_count = len(data.get("rtt_runs", []))
        matrix_cov = matrix_coverage_summary(data)
        rtt_cov = rtt_mode_summary(data)
        print(f"Matrix runs: {matrix_count}")
        print(f"RTT runs: {rtt_count}")
        print(
            "Canonical matrix coverage: "
            f"{matrix_cov['verified_pairs']}/{matrix_cov['expected_pairs']} verified"
        )
        if matrix_cov["pending_pairs"]:
            pending_text = ", ".join(
                f"{p['pair_a']} vs {p['pair_b']}" for p in matrix_cov["pending_pairs"]
            )
            print(f"Pending matrix pairs: {pending_text}")
        else:
            print("Pending matrix pairs: none")
        public = rtt_cov["modes"]["Public"]
        unlisted = rtt_cov["modes"]["Unlisted"]
        print(
            "RTT summary (Public): "
            f"entries={public['entries']}, trials={public['trials']}, "
            f"weighted_avg={public['weighted_avg_rtt_ms']} ms"
        )
        print(
            "RTT summary (Unlisted): "
            f"entries={unlisted['entries']}, trials={unlisted['trials']}, "
            f"weighted_avg={unlisted['weighted_avg_rtt_ms']} ms"
        )
        delta = rtt_cov.get("public_minus_unlisted_ms")
        if delta is None:
            print("RTT delta (Public - Unlisted): unavailable")
        else:
            print(f"RTT delta (Public - Unlisted): {delta} ms")
        print(f"Data: {DATA_PATH}")
        print(f"Matrix report: {MATRIX_RESULTS_PATH}")
        print(f"RTT report: {RTT_RESULTS_PATH}")
        return 0

    if args.command == "next":
        matrix_cov = matrix_coverage_summary(data)
        rtt_cov = rtt_mode_summary(data)
        print("Next recommended evidence logging commands:")
        if matrix_cov["pending_pairs"]:
            print("")
            print("Matrix:")
            for p in matrix_cov["pending_pairs"]:
                pair_a = p["pair_a"]
                pair_b = p["pair_b"]
                print(
                    "python scripts/online_validation_tool.py add-matrix "
                    f"--pair-a \"{pair_a}\" --pair-b \"{pair_b}\" "
                    "--result PASS --build-a \"<build-a>\" --build-b \"<build-b>\" "
                    "--notes \"<join/match stability notes>\""
                )
        else:
            print("")
            print("Matrix: all canonical pairs are verified.")

        print("")
        print("RTT:")
        for mode in ("Public", "Unlisted"):
            mode_row = rtt_cov["modes"][mode]
            if mode_row["entries"] == 0:
                print(
                    "python scripts/online_validation_tool.py add-rtt "
                    f"--mode {mode} --runs 5 --avg-rtt-ms <avg-ms> "
                    "--disconnects <n> --host-build \"<host-build>\" "
                    "--client-build \"<client-build>\" --notes \"<session notes>\""
                )
        if (
            rtt_cov["modes"]["Public"]["entries"] > 0
            and rtt_cov["modes"]["Unlisted"]["entries"] > 0
        ):
            print("Both RTT modes have data; add more alternating runs if confidence is low.")
        print("")
        print("Then refresh reports:")
        print("python scripts/online_validation_tool.py render")
        return 0

    if args.command == "seed-defaults":
        added = seed_default_matrix_entries(data)
        _save_and_render(data)
        print(f"Seeded default matrix entries: {added}")
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
