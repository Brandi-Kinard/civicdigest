"""
format_for_mlx.py — CivicDigest
Converts data/pairs.jsonl → data/train.jsonl, valid.jsonl, test.jsonl
in the exact format MLX LoRA expects.

Run: python scripts/format_for_mlx.py
"""

import json
import random
from pathlib import Path

PAIRS_FILE = Path("data/pairs_filtered.jsonl")
DATA_DIR   = Path("data")

TRAIN_RATIO = 0.80
VALID_RATIO = 0.10
TEST_RATIO  = 0.10

# This is the prompt template the MODEL will see at inference time.
# Must match what you use in app.py and summarize.py exactly.
PROMPT_TEMPLATE = (
    "### Meeting Minutes:\n{input}\n\n### Summary:\n{output}"
)

def main():
    if not PAIRS_FILE.exists():
        print("❌ data/pairs.jsonl not found — run generate_pairs.py first")
        return

    pairs = []
    with open(PAIRS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))

    print(f"📊 Loaded {len(pairs)} pairs")

    if len(pairs) < 20:
        print("⚠️  Very few pairs — scrape more data before training")

    # Shuffle with fixed seed for reproducibility
    random.seed(42)
    random.shuffle(pairs)

    n = len(pairs)
    n_train = int(n * TRAIN_RATIO)
    n_valid = int(n * VALID_RATIO)

    splits = {
        "train": pairs[:n_train],
        "valid": pairs[n_train:n_train + n_valid],
        "test":  pairs[n_train + n_valid:],
    }

    for split_name, split_pairs in splits.items():
        out_path = DATA_DIR / f"{split_name}.jsonl"
        with open(out_path, "w") as f:
            for pair in split_pairs:
                formatted = PROMPT_TEMPLATE.format(
                    input=pair["input"].strip(),
                    output=pair["output"].strip(),
                )
                f.write(json.dumps({"text": formatted}) + "\n")
        print(f"   ✅ {split_name}.jsonl — {len(split_pairs)} examples")

    print(f"\n{'='*60}")
    print("Ready to train. Run:")
    print()
    print("  mlx_lm.lora \\")
    print("    --model mlx-community/SmolLM2-1.7B-Instruct \\")
    print("    --train \\")
    print("    --data ./data \\")
    print("    --iters 500 \\")
    print("    --batch-size 2 \\")
    print("    --num-layers 8 \\")
    print("    --learning-rate 1e-4")

if __name__ == "__main__":
    main()
