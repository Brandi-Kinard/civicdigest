"""
summarize.py — CivicDigest CLI
Usage:
    python summarize.py "paste meeting minutes text here"
    python summarize.py --file path/to/minutes.txt
"""

import sys
import argparse
from pathlib import Path
from mlx_lm import load, generate

MODEL_PATH = "civicdigest-model"

def summarize(text: str) -> str:
    model, tokenizer = load(MODEL_PATH)
    prompt = f"### Meeting Minutes:\n{text.strip()}\n\n### Summary:"
    response = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=300,
        verbose=False,
    )
    return response

def main():
    parser = argparse.ArgumentParser(
        description="CivicDigest — summarize city council meeting minutes"
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Meeting minutes text (wrap in quotes)",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        help="Path to a .txt file containing meeting minutes",
    )
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: file not found: {args.file}")
            sys.exit(1)
        text = path.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("Reading from stdin... (Ctrl+D when done)")
        text = sys.stdin.read()

    if not text.strip():
        print("Error: no input text provided.")
        sys.exit(1)

    print("\n--- Summary ---\n")
    print(summarize(text))
    print()

if __name__ == "__main__":
    main()
