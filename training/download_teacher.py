"""Pre-stage the teacher checkpoint to the project dir (PLAN.md §6.3).

Run on a RUN node (has internet). bf16 Qwen3.6-27B is ~54GB; switch BPX_TEACHER_HF to the
AWQ-INT4 variant (~15GB) if you're serving on a 40GB A100. Idempotent.
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-stage the teacher for offline vLLM")
    parser.add_argument("--repo", default=os.environ.get("BPX_TEACHER_HF", "Qwen/Qwen3.6-27B"))
    parser.add_argument("--out", default=os.environ.get("BPX_TEACHER_DIR"))
    args = parser.parse_args()
    if not args.out:
        raise SystemExit("set --out or BPX_TEACHER_DIR (source training/config.sh first)")

    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        repo_id=args.repo,
        local_dir=args.out,
        allow_patterns=["*.safetensors", "*.json", "*.txt", "tokenizer*", "*.model"],
    )
    print(f"[download] {args.repo} -> {path}")


if __name__ == "__main__":
    main()
