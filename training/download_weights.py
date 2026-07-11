"""Pre-stage the unquantized Qwen3-8B checkpoint to the shared FS (PLAN.md §7.2).

Run on the ACCESS/login node (which has internet). Compute nodes then load it fully
offline (HF_HUB_OFFLINE=1). Idempotent — huggingface_hub skips files already present.

    source training/config.sh
    python training/download_weights.py
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-stage base weights for offline training")
    parser.add_argument("--repo", default=os.environ.get("BPX_BASE_HF", "Qwen/Qwen3-8B"))
    parser.add_argument("--out", default=os.environ.get("BPX_BASE_DIR"))
    args = parser.parse_args()
    if not args.out:
        raise SystemExit("set --out or BPX_BASE_DIR (source training/config.sh first)")

    os.environ["HF_HUB_OFFLINE"] = "0"  # this step is the one that IS allowed online
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        repo_id=args.repo,
        local_dir=args.out,
        # weights + tokenizer + config; skip the .gguf/.onnx mirrors some repos ship
        allow_patterns=["*.safetensors", "*.json", "*.txt", "tokenizer*", "*.model"],
    )
    print(f"[download] {args.repo} -> {path}")


if __name__ == "__main__":
    main()
