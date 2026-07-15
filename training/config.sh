# Shared config for the Phase-2 training pipeline (HPI SCI HPC). `source` before running.
# Jobs run in Enroot/Pyxis containers on Slurm; see training/README.md.

# Slurm allocation for -A. NOT your login — a short account name. VERIFY on the cluster:
#   sacctmgr show assoc user="$USER" format=account,user,partition
export BPX_ACCOUNT="${BPX_ACCOUNT:-philipp.mattar}"                       # <-- likely your username; confirm with sacctmgr
# Workspace for BIG artifacts (16GB base weights, venv, hf-cache, llama.cpp, adapters).
# MUST NOT be your git checkout, or those land inside the repo. $HOME is on the shared FS
# and visible from every node (200GB quota — see training/README.md for the budget).
export BPX_PROJECT_DIR="${BPX_PROJECT_DIR:-$HOME/bpx-work}"

# Local-only: SSH target for copying results back to your laptop (NOT used by cluster jobs).
# Format: user@access-node. Reach it over the *Scientific Compute* VPN (not the HPI VPN).
export BPX_CLUSTER_SSH="${BPX_CLUSTER_SSH:-philipp.mattar@hpc.sci.hpi.de}"

# Partitions (HPI SCI HPC — set --time explicitly; default is 8h)
export BPX_PARTITION_SHORT="${BPX_PARTITION_SHORT:-gpu-shortrun}"   # 1h  — G1 smoke
export BPX_PARTITION_BATCH="${BPX_PARTITION_BATCH:-gpu-batch}"      # 7d  — real training / teacher gen

# Pyxis/Enroot container: NGC PyTorch has CUDA + torch prebuilt for H100/Blackwell.
export BPX_IMAGE="${BPX_IMAGE:-nvcr.io#nvidia/pytorch:25.01-py3}"

# Models
export BPX_BASE_HF="${BPX_BASE_HF:-Qwen/Qwen3-8B}"                  # unquantized student base (§3)
export BPX_OLLAMA_BASE_TAG="${BPX_OLLAMA_BASE_TAG:-qwen3:8b}"       # matching Ollama serve tag

# Derived paths on the shared FS (/sc/home or /sc/projects — visible on all nodes)
export BPX_BASE_DIR="$BPX_PROJECT_DIR/models/qwen3-8b"             # pre-staged base weights
export BPX_WORK_DIR="$BPX_PROJECT_DIR/work"                        # adapters, dummy data, gguf, logs
export BPX_VENV="$BPX_PROJECT_DIR/venv"                            # training deps (built by setup_env.sh)
export LLAMA_CPP="$BPX_PROJECT_DIR/llama.cpp"                      # for GGUF adapter conversion
export HF_HOME="$BPX_PROJECT_DIR/hf-cache"                         # HF cache on shared NVMe

# Big *transient* artifacts (the teacher weights + its HF cache during data-gen) go on scratch,
# NOT home, to protect the 200GB home quota. Global scratch is huge (~450TB) but ephemeral —
# fine for re-downloadable model weights. Used by the later teacher-generation stage.
export BPX_SCRATCH_DIR="${BPX_SCRATCH_DIR:-/sc/scratch/$USER/bpx}"
export BPX_TEACHER_HF="${BPX_TEACHER_HF:-Qwen/Qwen2.5-72B-Instruct-AWQ}"   # ~40GB, 1x H100 via vLLM
