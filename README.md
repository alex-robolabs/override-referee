# Override Referee

Ask the ref anything about **Override**, the VEX V5 Robotics Competition 2026-2027 game. Built by the Robolabs Summer Academy 2026 curriculum: the same retrieval system students build in the Thursday lab, gift-wrapped as a web app they keep all season.

**Live app:** https://alex-robolabs.github.io/override-referee/

**The lab notebook:** [`Override_Referee_Lab.ipynb`](Override_Referee_Lab.ipynb). Open it in Colab and press Run All.

## What is in here

| File | What it is |
|---|---|
| `index.html` | The Override Referee web app (GitHub Pages serves this) |
| `embeddings.json` | Precomputed rule embeddings (quantized `Xenova/all-MiniLM-L6-v2`) |
| `rules.json` | Every rule and definition from the Override Game Manual v1.0, one chunk per rule |
| `extract_rules.py` | The build-time script that parsed the manual PDF into `rules.json` |
| `Override_Referee_Lab.ipynb` | The 25 minute retrieval lab (Colab, Run All friendly) |
| `FACILITATOR_KEY.md` | Facilitator timing, snags, and challenge answer key |

## How the app works

- The 200 or so rule chunks were embedded once at build time and shipped as `embeddings.json`.
- Your question is embedded in your browser with transformers.js and the quantized `Xenova/all-MiniLM-L6-v2` model (about 25 MB, downloaded once from a CDN, then cached).
- Cosine similarity over the shipped vectors ranks the rules; the top matches render as cards.
- While the model warms up (or if the CDN is unreachable), searches run in "quick match" mode: plain keyword overlap, instant but literal. "Meaning match" turns on when the model is ready.
- No server, no API key, nothing leaves your phone except the one-time model download. The app does need internet the first time so the CDN can deliver the model.

The manual PDF itself is not distributed in this repo. Download it from the official VEX Robotics site; `extract_rules.py` expects it as `v5rc-override-1.0.pdf`.

## Rebuilding

```bash
pip install pymupdf
python extract_rules.py v5rc-override-1.0.pdf   # writes rules.json
node build_embeddings.mjs                        # writes embeddings.json
```

---

Game Manual text © 2026 VEX Robotics, Inc. Used with permission for educational purposes at Robolabs Summer Academy.
