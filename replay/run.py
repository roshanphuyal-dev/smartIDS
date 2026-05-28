import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Short launcher for CICIDS replay demo")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--forward-all-predictions", action="store_true")
    parser.add_argument("--csv-path", default="ml/data/cicids2017_test.csv")
    args = parser.parse_args()

    command = [
        sys.executable,
        "tools/replay_cicids_csv.py",
        "--csv-path",
        args.csv_path,
        "--limit",
        str(args.limit),
        "--interval",
        str(args.interval),
    ]

    if args.forward_all_predictions:
        command.append("--forward-all-predictions")

    subprocess.run(command, check=False)


if __name__ == "__main__":
    main()
