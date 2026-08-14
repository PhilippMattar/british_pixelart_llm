"""Real QLoRA training for one persona adapter (PLAN.md §7.2).

Generalises g1_smoke.py from the throwaway smoke test to a production run: real committed
data (training/data/{persona}_train.jsonl), a held-out val split for an eval-loss curve, the
§7.2 hyperparameters (r=16 / a=32, lr 2e-4 cosine, 3 epochs, seq 2048, effective batch 16),
and — the one real quality lever over G1 — **completion-only loss**: loss is computed on the
assistant answer only, so the adapter learns to *speak in voice*, not to predict the user's
questions.

Same transparent transformers + peft + trl/Trainer + bitsandbytes stack as G1 (Unsloth is the
faster option for later, Ch. 05). The Qwen3 *non-thinking* chat template is enforced so training
matches serving (§3 lock). Run inside the training venv on a GPU node with the base weights
pre-staged (offline). Submit two runs (british, scottish) via slurm/train.sbatch.

    python train_qlora.py --base "$BPX_BASE_DIR" \
        --data data/british_train.jsonl --val data/british_val.jsonl \
        --out "$BPX_WORK_DIR/british-adapter"
"""

from __future__ import annotations

import argparse
import os

# pyxis / the NGC image leave LOCAL_RANK set in the container env. accelerate reads that as a
# torchrun-style distributed launch and calls init_process_group(env://), which then needs
# WORLD_SIZE/MASTER_ADDR — but this is a single-GPU job. Dropping the rendezvous vars before
# accelerate initialises makes it run single-process (DistributedType.NO). Must precede the
# transformers/trl imports below, which pull accelerate in. (Same reason as g1_smoke.py.)
for _var in ("LOCAL_RANK", "RANK", "WORLD_SIZE"):
    os.environ.pop(_var, None)

from pathlib import Path  # noqa: E402

import torch  # noqa: E402
from datasets import load_dataset  # noqa: E402
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training  # noqa: E402
from transformers import (  # noqa: E402
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

# Standard attention + MLP projections for Qwen-family models (matches g1_smoke.py).
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real QLoRA training for one persona adapter")
    p.add_argument("--base", required=True, help="path to the pre-staged Qwen3-8B checkpoint")
    p.add_argument("--data", required=True, help="train JSONL with a 'messages' field")
    p.add_argument("--val", help="optional val JSONL (same format) -> eval-loss curve")
    p.add_argument("--out", required=True, help="output dir for the LoRA adapter")
    # §7.2 starting hyperparameters. effective batch = batch-size * grad-accum = 16.
    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--seq-len", type=int, default=2048)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument(
        "--loss",
        choices=("completion", "full"),
        default="completion",
        help="completion = loss on the assistant answer only (learns voice, not the questions); "
        "full = loss over the whole rendered turn, like the G1 smoke test",
    )
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args()


def build_tokenize_fn(tokenizer, seq_len: int, completion_only: bool):
    """Render each {messages} row to input_ids + labels with the Qwen3 non-thinking template.

    For completion-only loss we mask the prompt: render the conversation minus the final
    assistant turn (add_generation_prompt=True) and the full conversation, then mask the shared
    token prefix. That prefix ends exactly at the `<|im_start|>assistant\\n` header in *both*
    template variants — whether or not the non-thinking template injects an empty <think></think>
    block into the generation prompt — because the empty-think tokens diverge from the real
    answer tokens, stopping the common prefix at the header. So the answer (and its closing
    <|im_end|>, which teaches the model to stop) is always trained on; the question never is.
    """

    def render_ids(messages, add_generation_prompt: bool) -> list[int]:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=add_generation_prompt,
            enable_thinking=False,  # §3 lock: personas never think; matches serving.
        )

    def fn(example: dict) -> dict:
        messages = example["messages"]
        full_ids = render_ids(messages, add_generation_prompt=False)[:seq_len]
        labels = list(full_ids)
        if completion_only:
            prompt_ids = render_ids(messages[:-1], add_generation_prompt=True)
            n = 0
            while n < len(prompt_ids) and n < len(full_ids) and prompt_ids[n] == full_ids[n]:
                n += 1
            for i in range(min(n, len(labels))):
                labels[i] = -100
        return {"input_ids": full_ids, "attention_mask": [1] * len(full_ids), "labels": labels}

    return fn


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
        dtype=torch.bfloat16,  # transformers 5.x renamed torch_dtype -> dtype
        device_map="auto",
    )
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=TARGET_MODULES,
        ),
    )
    model.print_trainable_parameters()
    model.config.use_cache = False  # incompatible with training; silences the warning.

    tokenize = build_tokenize_fn(tokenizer, args.seq_len, completion_only=args.loss == "completion")
    train_ds = load_dataset("json", data_files=args.data, split="train")
    train_ds = train_ds.map(tokenize, remove_columns=train_ds.column_names)
    eval_ds = None
    if args.val and Path(args.val).exists():
        eval_ds = load_dataset("json", data_files=args.val, split="train")
        eval_ds = eval_ds.map(tokenize, remove_columns=eval_ds.column_names)

    trainer = Trainer(
        model=model,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        # Pads input_ids/attention_mask, and pads labels with -100 (ignored by the loss).
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, label_pad_token_id=-100),
        args=TrainingArguments(
            output_dir=args.out,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            per_device_eval_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_ratio=0.05,
            bf16=True,
            logging_steps=10,
            eval_strategy="epoch" if eval_ds is not None else "no",
            save_strategy="epoch",
            save_total_limit=1,
            load_best_model_at_end=eval_ds is not None,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            remove_unused_columns=False,
            report_to="none",
            seed=args.seed,
        ),
    )
    trainer.train()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)  # adapter_config.json + adapter_model.safetensors only
    tokenizer.save_pretrained(out)
    print(f"[train] adapter saved to {out}")


if __name__ == "__main__":
    main()
