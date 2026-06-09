# train_lora.py  — run this in Google Colab on an A100/T4 GPU
# pip install transformers peft trl accelerate bitsandbytes datasets

import json, torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer
from data.synthetic_generator import build_dataset

# ── 1. Generate training data ─────────────────────────────────────────────
print("Building dataset...")
raw = build_dataset(2000)
texts = [r["prompt"] + r["completion"] for r in raw]
hf_dataset = Dataset.from_dict({"text": texts})

# ── 2. Load model ─────────────────────────────────────────────────────────
MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    device_map="auto",
    load_in_4bit=True,
    torch_dtype=torch.bfloat16,
)

# ── 3. LoRA config (max rank=32 per competition rules) ────────────────────
lora_config = LoraConfig(
    r=32,
    lora_alpha=64,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ── 4. Training arguments ─────────────────────────────────────────────────
training_args = TrainingArguments(
    output_dir="./lora_output",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    warmup_steps=50,
    learning_rate=2e-4,
    fp16=True,
    logging_steps=25,
    save_strategy="epoch",
    optim="paged_adamw_8bit",
)

# ── 5. Train ──────────────────────────────────────────────────────────────
trainer = SFTTrainer(
    model=model,
    train_dataset=hf_dataset,
    dataset_text_field="text",
    max_seq_length=2048,
    args=training_args,
)
trainer.train()

# ── 6. Save adapter (this is your submission.zip contents) ────────────────
model.save_pretrained("./submission_adapter")
tokenizer.save_pretrained("./submission_adapter")
print("✓ Adapter saved to ./submission_adapter")
print("  → zip -r submission.zip submission_adapter/adapter_config.json submission_adapter/adapter_model.safetensors")

# ── 7. LOGPROB FILTERING (Progress Prize winner's technique) ──────────────
# After first training pass, run this to find hard problems, retrain on those
def filter_hard_problems(model, tokenizer, dataset, threshold=-2.0):
    """Keep only samples where model struggles (low logprob = hard)."""
    hard = []
    model.eval()
    with torch.no_grad():
        for item in dataset:
            inputs = tokenizer(item["text"], return_tensors="pt").to(model.device)
            outputs = model(**inputs, labels=inputs["input_ids"])
            avg_logprob = -outputs.loss.item()  # negative NLL = avg logprob
            if avg_logprob < threshold:
                hard.append(item)
    print(f"Hard problems: {len(hard)}/{len(dataset)}")
    return hard
