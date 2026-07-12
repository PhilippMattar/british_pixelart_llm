# training/ — Phase-2 fine-tuning (HPI SCI HPC)

Cluster-side scripts for the persona LoRAs (R7). Edited here, run on the **HPI Scientific
Compute HPC** (Slurm + Enroot/Pyxis containers). See PLAN.md §6–§7.

> **Cluster shape** (docs.sc.hpi.de): jobs run in **Pyxis/Enroot containers**, not a bare
> env/module setup. GPUs via `--gpus=N` + `-C GPU_MEM:80GB` (H100 80GB). Partitions:
> `gpu-shortrun` (1h), `gpu-batch` (7d). Shared NVMe at `/sc/projects/<group>/<project>`.
> This adapts PLAN.md §7.2's "uv + module" assumption to containers.

## G1 gate — do this first (highest-risk item, §7.1)

G1 trains a **throwaway** 100-sample LoRA on Qwen3-8B in minutes, converts it to a GGUF
adapter, and serves it via Ollama. It exists to catch Qwen3 GGUF-LoRA conversion problems
*before* any real data work. **Pass** ⇒ Qwen3-8B is confirmed; everything downstream
proceeds. **Fail after ~2 days** ⇒ fall back to Qwen2.5-7B-Instruct (change `BPX_BASE_HF`
and `BPX_OLLAMA_BASE_TAG`).

### 0. Configure (once)

Edit [config.sh](config.sh): set `BPX_ACCOUNT` (your Slurm `-A`) and `BPX_PROJECT_DIR`
(your `/sc/projects/<group>/<project>`). Everything else has sensible defaults.

### 1. Build the env + stage weights (on the login/interactive node — has internet)

```bash
source training/config.sh
bash   training/env/setup_env.sh        # venv (inherits container torch) + llama.cpp clone
python training/download_weights.py     # pre-stage Qwen3-8B to $BPX_BASE_DIR (offline after this)
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
