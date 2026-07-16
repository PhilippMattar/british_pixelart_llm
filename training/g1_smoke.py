"""G1 gate — dummy QLoRA smoke test on Qwen3-8B (PLAN.md §7.1).

Trains a throwaway LoRA on ~100 samples in a few minutes to validate the whole
train -> adapter -> GGUF -> Ollama pipeline *before* investing in real data. The point of
G1 is to surface Qwen3 GGUF-LoRA conversion issues early; if it can't be made to work in
~2 days, the plan falls back to Qwen2.5-7B-Instruct.

Uses the transparent transformers + peft + trl + bitsandbytes stack (Unsloth is the faster
option for the real runs, Ch. 05). The Qwen3 *non-thinking* chat template is enforced so
training matches serving (§3). Run inside the training venv on a GPU node; the base weights
must be pre-staged so it can run offline.
"""

from __future__ import annotations

import argparse
import os

# pyxis / the NGC image leave LOCAL_RANK set in the container env. accelerate reads that as a
# torchrun-style distributed launch and calls init_process_group(env://), which then needs
# WORLD_SIZE/MASTER_ADDR — but this is a single-GPU job. Dropping the rendezvous vars before
# accelerate initialises makes it run single-process (DistributedType.NO). Must precede the
# transformers/trl imports below, which pull accelerate in.
for _var in ("LOCAL_RANK", "RANK", "WORLD_SIZE"):
    os.environ.pop(_var, None)

from pathlib import Path  # noqa: E402

import torch  # noqa: E402
from datasets import load_dataset  # noqa: E402
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: E402
from trl import SFTConfig, SFTTrainer  # noqa: E402

# Standard attention + MLP projections for Qwen-family models.
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="G1 dummy QLoRA smoke test")
    parser.add_argument("--base", required=True, help="path to the pre-staged Qwen3-8B checkpoint")
    parser.add_argument("--data", required=True, help="JSONL with a 'messages' field")
    parser.add_argument("--out", required=True, help="output dir for the LoRA adapter")
    parser.add_argument("--max-steps", type=int, default=30, help="tiny by design (smoke test)")
    parser.add_argument("--seq-len", type=int, default=1024)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        quantization_config=quant,
        dtype=torch.bfloat16,   # transformers 5.x renamed torch_dtype -> dtype
        device_map="auto",
    )
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(
        model,
        LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=TARGET_MODULES,
        ),
    )
    model.print_trainable_parameters()

    dataset = load_dataset("json", data_files=args.data, split="train")

    def render(example: dict) -> dict:
        # Qwen3 NON-thinking template — no <think> blocks, matching serving (§3 lock).
        text = tokenizer.apply_chat_template(
            example["messages"],
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        return {"text": text}

    dataset = dataset.map(render, remove_columns=dataset.column_names)

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        # TRL >=1.0 takes the tokenizer as `processing_class`; pass it explicitly so nothing
        # tries to re-fetch it (jobs run with HF_HUB_OFFLINE=1).
        processing_class=tokenizer,
        args=SFTConfig(
            output_dir=args.out,
            max_steps=args.max_steps,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            warmup_ratio=0.05,
            bf16=True,
            logging_steps=5,
            max_length=args.seq_len,   # TRL >=1.0 renamed max_seq_length -> max_length
            dataset_text_field="text",
            report_to="none",
        ),
    )
    trainer.train()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)      # adapter_config.json + adapter_model.safetensors
    tokenizer.save_pretrained(out)
    print(f"[G1] adapter saved to {out}")


if __name__ == "__main__":
    main()
