# 05 — QLoRA training on a SLURM cluster

## Goal

Stand up the cluster-side training pipeline and prove it end-to-end with **G1**: a throwaway
QLoRA run on the real Qwen3-8B base that trains an adapter in a few minutes, so the whole
`train → adapter` machinery is known-good *before* any real data or long run. Everything
downstream in fine-tuning waits on G1 passing (PLAN.md §7.1).

## Why it exists

The persona adapters (R2) are LoRAs over Qwen3-8B, and that base is a locked decision — a LoRA
learns deltas tied to one base's exact weights (§3). Getting a Qwen3 adapter to convert and
serve is the single highest-risk item in the project, so G1 de-risks it on a dummy run: if the
pipeline can't be made to work in ~2 days, the plan falls back to Qwen2.5-7B-Instruct. Training
happens on the HPI SCI HPC because an 8B QLoRA needs an 80GB-class GPU we don't have locally.

## What was built

- `training/config.sh` — one sourced file of truth for the cluster: account, partitions, GPU
  constraint, container image, base/teacher model ids, and all derived paths (`BPX_BASE_DIR`,
  `BPX_WORK_DIR`, `BPX_VENV`, `LLAMA_CPP`, …) under `BPX_PROJECT_DIR`.
- `training/env/import_image.sh` — one-time `enroot import` of the NGC PyTorch image to a
  squashfs (`$BPX_SQSH`); `env/setup_env.sh` builds the training venv (`transformers`, `peft`,
  `trl`, `bitsandbytes`) on the shared FS and clones llama.cpp; `env/requirements.txt` pins them.
- `training/download_weights.py` — pre-stages the unquantized Qwen3-8B on a run node (online),
  so jobs run with `HF_HUB_OFFLINE=1`.
- `training/g1_smoke.py` — the QLoRA itself: 4-bit NF4 quantised base + a LoRA (`r=16`,
  `alpha=32`) on the standard Qwen attention/MLP projections, trained with `trl`'s `SFTTrainer`
  over the **Qwen3 non-thinking** chat template. `make_dummy_data.py` gives it ~100 throwaway
  British-flavoured samples.
- `training/slurm/g1.sbatch` + `training/submit_g1.sh` — the batch job (dummy data → QLoRA →
  GGUF export) and its launcher, which supplies `-A/-p/-C` and the repo path.

## Core concepts

- **QLoRA** — freeze the base in 4-bit (NF4, double-quantised), train only small LoRA adapter
  matrices in bf16. This is what makes an 8B fine-tune fit one GPU; you save ~30MB of adapter,
  not a 16GB model.
- **One chat template everywhere** — the Qwen3 *non-thinking* template (`enable_thinking=False`)
  is used in training, eval, and serving, identically. A train/serve mismatch silently degrades
  the adapter, and personas must never emit `<think>` blocks (§3).
- **Pyxis/enroot containers** — the cluster runs container images (not bare modules) via
  `srun --container-image=…`. Import the image once to a squashfs so each job mounts it in
  seconds instead of re-importing (~15 min) and blowing the time limit.
- **Three node roles** — you *submit* from a **run** node (has internet, can `srun`/`sbatch`);
  jobs execute on **compute** nodes (offline, GPUs); the **login** node forbids these commands.
- **Offline by construction** — weights and the venv are pre-staged, jobs export
  `HF_HUB_OFFLINE=1`; nothing in a batch job may touch the network.

## Resources

- QLoRA paper — <https://arxiv.org/abs/2305.14314>
- PEFT LoRA conceptual guide — <https://huggingface.co/docs/peft/conceptual_guides/lora>
- TRL `SFTTrainer` — <https://huggingface.co/docs/trl/sft_trainer>
- bitsandbytes (4-bit) — <https://huggingface.co/docs/bitsandbytes/main/en/index>
- NVIDIA pyxis / enroot — <https://github.com/NVIDIA/pyxis> · <https://github.com/NVIDIA/enroot>
- Slurm `sbatch` — <https://slurm.schedmd.com/sbatch.html>
- Unsloth (the faster stack for the real runs) — <https://docs.unsloth.ai/>

## Gotchas

- **`#SBATCH` can't expand variables** — pass `-A/-p/-C` on the `sbatch` command line (from
  `submit_g1.sh`), not in the script header.
- **Slurm runs a *spooled copy*** of the batch script (`/var/spool/slurmd/…`), so `$0` and
  `source ./config.sh` fail inside the job — `submit_g1.sh` passes the repo path as
  `BPX_TRAINING_DIR` via `--export=ALL,…`.
- **Partition submission type matters** — `gpu-shortrun`/`gpu-interactive` reject `sbatch`
  (they're `srun`/`salloc` only); batch jobs go to `gpu-batch`.
- **Pick the GPU by SKU** — `-C GPU_SKU:A100`. V100/2080Ti lack bf16, GH200 is ARM; a bare
  `GPU_MEM:80GB` matched nothing on the interactive partition.
- **`LOCAL_RANK` leaks from the container** — accelerate reads it as a distributed launch and
  demands `WORLD_SIZE`/`MASTER_ADDR`. Pop `LOCAL_RANK/RANK/WORLD_SIZE` *before* importing
  transformers/trl so it runs single-process.
- **Don't use `bash -lc`** — a login shell re-activates conda `(base)` inside the container and
  shadows the venv's `python`; use `bash -c` and `source "$BPX_VENV/bin/activate"`.
- **TRL ≥1.0 / transformers 5.x API drift** — `max_seq_length` → `max_length`, the tokenizer is
  `processing_class`, and `torch_dtype` → `dtype`. Read the installed wheel, don't trust old
  tutorials.
- **OOM at image import** (exit 137) — give the import job real CPU/RAM (`-c 8 --mem=64G`).
- **Home quota (200GB) fills fast** — weights + venv + squashfs belong on a `/sc/projects` share
  (`BPX_PROJECT_DIR`), not `$HOME`.
