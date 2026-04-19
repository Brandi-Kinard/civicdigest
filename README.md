# CivicDigest 🏛️

A fine-tuned language model that reads city council meeting minutes and produces plain English summaries of what was decided.

Your city makes decisions every month — about roads, zoning, budgets, public safety — that directly affect your life. The minutes are public record. But they're written in a language most people never learned to read.

CivicDigest reads them for you.

---

## What it does

Paste raw meeting minutes. Get a 2-paragraph plain English summary covering:
- What was voted on and how
- What was proposed or discussed
- What directly affects residents

---

## Model

- **Base:** SmolLM2-1.7B-Instruct
- **Method:** LoRA fine-tuning via MLX on Apple Silicon
- **Training data:** City council meeting minutes from Chicago, Seattle, Denver, Phoenix, Detroit, Oakland, New York City, and San Francisco
- **HuggingFace:** [Brandi-Kinard/civicdigest-smollm2-1.7b](https://huggingface.co/Brandi-Kinard/civicdigest-smollm2-1.7b)

---

## Run locally

**Requirements:** Apple Silicon Mac (M1/M2/M3), Python 3.11+

```bash
git clone https://github.com/Brandi-Kinard/civicdigest.git
cd civicdigest
python3.11 -m venv venv
source venv/bin/activate
pip install mlx-lm streamlit
```

Download the fused model weights from HuggingFace and place in `civicdigest-model/`.

**Streamlit app:**
```bash
streamlit run app.py
```

**CLI:**
```bash
python summarize.py "paste minutes text here"
python summarize.py --file path/to/minutes.txt
```

---

## Try it

Live demo: [huggingface.co/spaces/Brandi-Kinard/civicdigest](https://huggingface.co/spaces/Brandi-Kinard/civicdigest)

---

## Limitations

- Model may occasionally misstate specific dollar amounts or vote counts — always verify against official records
- Performs best on full meeting transcripts; sparse agenda-only text produces shorter summaries
- Optimized for US city council meetings; other government body formats may vary

---

## License

MIT

---

*Built by [Brandi Kinard](https://www.linkedin.com/in/brandikinard)*
