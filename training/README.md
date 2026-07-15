# training/ — Phase-2 fine-tuning (HPI SCI HPC)

Cluster-side scripts for the persona LoRAs (R7). Edited here, run on the **HPI Scientific
Compute HPC** (Slurm + Enroot/Pyxis containers). See PLAN.md §6–§7.

> **Cluster shape** (verified with `sinfo`/`sacctmgr`, 2026-07-12): jobs run in
> **Pyxis/Enroot containers**, not a bare env/module setup — this adapts PLAN.md §7.2's
> "uv + module" assumption. Partitions: `gpu-interactive` (8h) · `gpu-shortrun` (1d) ·
> `gpu-batch` (7d). GPUs via `--gpus=N` + `-C GPU_SKU:A100`.
>
> **Why pin A100:** `g1_smoke.py` trains in bf16, which needs Ampere+ — but `gpu-interactive`
> also holds V100/2080Ti (no bf16) and GH200 (ARM, incompatible with our x86 container). The
> **H100s live only in the `aisc-*` partitions**, so don't chase `GPU_MEM:80GB` here; an A100
> 40GB is ample for an 8B QLoRA. Storage is `$HOME` on shared NVMe (200GB quota).

## G1 gate — do this first (highest-risk item, §7.1)

G1 trains a **throwaway** 100-sample LoRA on Qwen3-8B in minutes, converts it to a GGUF
adapter, and serves it via Ollama. It exists to catch Qwen3 GGUF-LoRA conversion problems
*before* any real data work. **Pass** ⇒ Qwen3-8B is confirmed; everything downstream
proceeds. **Fail after ~2 days** ⇒ fall back to Qwen2.5-7B-Instruct (change `BPX_BASE_HF`
and `BPX_OLLAMA_BASE_TAG`).

### 0. Configure (once)

Only one value needs checking — your Slurm account. On the cluster:

```bash
sacctmgr show assoc user=$USER format=account%30,user%20,partition%20
```

The `account` column is your `-A` value; if it differs from [config.sh](config.sh)'s
`BPX_ACCOUNT`, `export BPX_ACCOUNT=<real-account>` (or edit the file).

Everything else defaults sensibly. In particular `BPX_PROJECT_DIR` defaults to
`$HOME/bpx-work` — the workspace for the big artifacts (16GB weights, venv, hf-cache,
adapters). **Keep it separate from your git checkout**, or those land inside the repo:

```text
$HOME/britishpixelart_llm/   <- the git clone (code only)
$HOME/bpx-work/              <- BPX_PROJECT_DIR (weights, venv, work/ — never committed)
```

The scripts `mkdir -p` the workspace themselves; you don't create it.

### 1. Build the env + stage weights (on the login/interactive node — has internet)

```bash
source training/config.sh
bash   training/env/import_image.sh      # ONCE: registry -> $BPX_SQSH (~15-20 min, see gotchas)
bash   training/env/setup_env.sh         # venv (inherits container torch) + llama.cpp clone
python training/download_weights.py      # pre-stage Qwen3-8B to $BPX_BASE_DIR (offline after this)
```

### 2. Run G1 (batch, offline)

```bash
bash training/submit_g1.sh              # sbatch on gpu-shortrun; watch: squeue --me
# on success: $BPX_WORK_DIR/g1.gguf
```

### 3. Verify locally (needs Ollama)

```bash
source training/config.sh                 # for $BPX_CLUSTER_SSH and $BPX_WORK_DIR
rsync "$BPX_CLUSTER_SSH:$BPX_WORK_DIR/g1.gguf" models/adapters/g1.gguf
ollama create bpx-g1 -f models/Modelfile.g1
ollama run bpx-g1 "How's the weather?"    # coherent + faintly British => PASS
```

## Files

| File | Role |
|---|---|
| `config.sh` | shared vars (account, project dir, partitions, image, model, paths) |
| `env/requirements.txt` · `env/setup_env.sh` | training deps on the shared FS + llama.cpp clone |
| `download_weights.py` | pre-stage the unquantized Qwen3-8B (login node, online) |
| `make_dummy_data.py` | ~100 throwaway chat samples for the smoke test (stdlib) |
| `g1_smoke.py` | dummy QLoRA (transformers+peft+trl+bitsandbytes), Qwen3 non-thinking template |
| `export_gguf.sh` | PEFT adapter → GGUF via llama.cpp `convert_lora_to_gguf.py` |
| `slurm/g1.sbatch` · `submit_g1.sh` | the batch job + submit wrapper (supplies `-A`/`-p`) |

## Notes / gotchas

- **Never let a job pull from the registry.** Measured on this cluster: pyxis importing
  `nvcr.io#nvidia/pytorch:25.01-py3` costs **~15 min of job runtime, every time** (60 layers,
  ~20GB, unpack + mksquashfs) — a probe with `--time=00:15:00` was killed by its limit purely
  on the import, and a 40-min probe took 36 min wall. `env/import_image.sh` imports it once to
  `$BPX_SQSH`; jobs then mount that path and start in seconds.
- **Always pass `--mem` and `-c` to any job that does import a container.** The import is
  host-RAM hungry; with Slurm's default memory you get OOM-killed mid-import (`error code: 137`,
  `oom_kill event`) before your code runs. `-c 8 --mem=64G` suffices.
- **Your conda leaks into the container.** Enroot mounts `$HOME`, so an interactive
  (`--pty bash`) or login (`bash -lc`) shell sources `~/.bashrc`, activates your conda `base`,
  and shadows the container's python — you get `(base)` in the prompt and
  `ModuleNotFoundError: No module named 'torch'` *inside the PyTorch image*. Use `bash -c`
  (no rc files), or `conda deactivate` when poking around interactively. This matters most in
  `setup_env.sh`: building the venv on conda's python instead of the container's would inherit
  no torch and break training silently, so it now fails fast if torch isn't importable first.

- **Offline by default**: only `setup_env.sh` and `download_weights.py` use the network
  (login node). Batch jobs set `HF_HUB_OFFLINE=1`. If compute nodes *do* have internet this
  is just harmless caution.
- **Template must match serving**: `g1_smoke.py` uses `enable_thinking=False` (Qwen3
  non-thinking) — the same template the app serves (§3). Don't drift.
- **Version churn**: TRL's `SFTConfig`/`SFTTrainer` arg names shift between releases; if the
  smoke errors on an arg, check the installed TRL version. Unsloth is the faster real-run
  option (Ch. 05) but pins a torch/transformers matrix — layer it in only after G1 passes.
- **Not committed**: base weights + HF cache live on `/sc/projects` (never the repo); the
  dummy data + adapters are throwaway (gitignored).
