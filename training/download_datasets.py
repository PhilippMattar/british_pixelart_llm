"""Stage open instruction datasets for the prompt bank (PLAN.md §6.2).

Run on a RUN node (has internet). Currently Dolly-15k — human-written, CC-BY-SA (attribute it in
the README), and it ships as JSONL so build_bank.py can parse it with the stdlib alone. Add more
sources here if you want more variety, but mind the licence: keep everything redistributable for
the hand-in (that's why Alpaca — OpenAI-derived, non-commercial — is deliberately not here).
"""

from __future__ import annotations

import argparse
import os

DATASETS = {"dolly": "databricks/databricks-dolly-15k"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage instruction datasets for the prompt bank")
    parser.add_argument("--out", default=os.environ.get("BPX_DATASETS_DIR"))
    args = parser.parse_args()
    if not args.out:
        raise SystemExit("set --out or BPX_DATASETS_DIR (source training/config.sh first)")

    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import snapshot_download

    for name, repo in DATASETS.items():
        path = snapshot_download(
            repo_id=repo,
            repo_type="dataset",
            local_dir=os.path.join(args.out, name),
            allow_patterns=["*.jsonl", "*.json"],
        )
        print(f"[datasets] {repo} -> {path}")


if __name__ == "__main__":
    main()
