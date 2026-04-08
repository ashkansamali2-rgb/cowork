# ForensicNet — Project Context Document v3
## For continuing this project in a new Claude chat

Paste this entire document as your first message in any new Claude conversation.
Tell Claude: "I am continuing this project. Read this document fully before responding."

---

## Who I Am

I am Feargal (also goes by Ashkan Samali), a secondary school student in Ireland.
I am building a deepfake detection platform called **Cantivia** for **YSTE
(Young Scientist and Technology Exhibition)**. I placed 1st in Technology
Intermediate at YSTE 2026. I am returning to improve the system significantly.

I use **Claude Code** to implement all code changes. When Claude gives me prompts,
I pass them directly to Claude Code which edits my actual files.
I do not manually edit code myself.

GitHub repository: `ashkansamali2-rgb/forensicnet` (branch: main)
Local repo path: `/Users/ashkansamali/Vision/backbone/ForensicNet`
Python environment: `/Users/ashkansamali/forensicnet_env/bin/python3`

---

## Repository Structure

```
forensicnet/                          ← repo root
├── CONTEXT.md                        ← this file, lives at root
├── README.md                         ← project overview
├── forensicnet_nano/                 ← 5M proof of concept (image only, works)
├── forensicnet_75m/                  ← 75M validation backbone (needs retraining)
│   ├── models/
│   │   ├── backbone_75m.py           ← ForensicNet75M architecture
│   │   ├── decoder_75m.py            ← MAEDecoder75M (training only)
│   │   ├── backbone.py               ← Nano classes (TransformerBlock etc.)
│   │   ├── gated_repr.py             ← GatedRepresentation module
│   │   └── __init__.py
│   ├── train_75m.py                  ← backbone pretraining script
│   ├── train_heads.py                ← classifier head training
│   ├── test_backbone.py              ← 10-test diagnostic suite
│   ├── run.sh                        ← training launch script
│   ├── setup.sh                      ← server setup script
│   ├── requirements.txt              ← all dependencies
│   ├── 75m_subset_manifest.json      ← HuggingFace dataset manifest
│   └── CLAUDE.md                     ← Claude Code context for 75M
└── forensicnet_300m/                 ← 300M production backbone (built, not trained)
    ├── models/
    │   ├── backbone_300m.py          ← ForensicNet300M architecture
    │   ├── decoder_300m.py           ← MAEDecoder300M (training only)
    │   ├── gated_repr.py             ← copy of GatedRepresentation
    │   └── __init__.py
    ├── train_300m.py                 ← backbone pretraining (8x B200 DDP)
    ├── train_heads_300m.py           ← classifier head training
    ├── test_backbone_300m.py         ← 10-test diagnostic suite
    ├── run.sh                        ← training launch (--nproc_per_node=8)
    ├── setup.sh                      ← server setup
    ├── requirements.txt              ← all dependencies
    └── CLAUDE.md                     ← Claude Code context for 300M
```

---

## What Cantivia Is

A modular deepfake detection platform:
- A single **forensic backbone** learns universal frequency-domain representations
  across images, audio, and video
- Lightweight **classifier heads** (one per AI generator) bolt on top of the frozen backbone
- New generators detected by training only a new head (~30 min), no backbone retraining
- Backend: Rust/Axum + Python ML workers + NATS + PostgreSQL + Redis

Key insight: AI-generated content leaves artifacts in the **DCT frequency domain**.
ForensicNet operates exclusively in frequency space — it never sees raw pixels.

---

## Model Progression (the story for judges)

1. **ForensicNet-Nano (5M)** — `forensicnet_nano/` — proof of concept, images only.
   Validated the architecture approach. Learned what worked and what didn't.

2. **ForensicNet-75M (78.71M)** — `forensicnet_75m/` — full multimodal backbone.
   Handles images, audio, and video. Trained once (9 epochs, not enough).
   Needs retraining with fixes applied.

3. **ForensicNet-300M (301M)** — `forensicnet_300m/` — production backbone.
   Codebase built and ready. Needs GPU budget to train.

---

## Architecture — ForensicNet-75M and 300M

Both models share identical architecture. Only dimensions differ.

| Component | 75M | 300M |
|-----------|-----|------|
| Embedding dim | 640 | 1024 |
| Attention heads | 10 | 16 |
| Stem layers | 5 | 8 |
| Visual layers | 6 | 9 |
| Audio layers | 4 | 6 |
| Decoder dim | 320 | 512 |
| Decoder layers | 4 | 6 |
| Decoder heads | 5 | 8 |
| Parameters | ~78.71M | ~301.4M |

**Fixed for both models:**
- Input: [3, 128, 128] DCT frequency tensor for ALL modalities — never change
- Patch size: 4x4, 1024 patches — never change
- No spatial interpolation on frequency data — destroys forensic information
- torch.scatter in decoder (not torch.gather) — gradient flow fix
- Dropout 0.1 backbone, 0.0 decoder
- Z-score normalisation before GatedRepresentation
- bfloat16 mixed precision, no GradScaler needed
- Backbone trains on REAL data only

**DCT Preprocessing:**
- Resize to 1024x1024 → 2D DCT via scipy.fft.dctn orthonormal
- Three 128x128 bands: Low [:128,:128], Mid [448:576,448:576], High [896:,896:]
- Average across RGB → [3,128,128] → z-score normalise

**Audio:** mel + delta + delta-delta → [3,128,128]
**Video:** YCbCr → DCT per frame → 8-frame temporal pool → [3,128,128]

---

## Training Dataset

`ash12321/forensic-dataset` on HuggingFace — 169 healthy WebDataset tars, ~1.19TB
- Image: 122 tars, 185.9GB (ImageNet, COCO, WikiArt, Flickr30k)
- Audio: 32 tars, 49.2GB (LibriSpeech, ESC-50)
- Video: 15 tars, 956GB (AVA, UCF-101)
- 75M subset: 18 image + 12 audio + 4 video tars (~211.5GB)
- 300M target: 800K samples from full dataset
- Modality schedule: ["image","image","audio","video"] — 2:1:1 ratio

---

## What Went Wrong in the First 75M Training Run

Hardware: DigitalOcean H100, 9 epochs, ~€200. Final loss: 0.7351 (not converged).

- Loss curve: 0.7855 → 0.7451 → ... → 0.7351 (still descending at epoch 8)
- Cosine similarity: 0.9992 (all embeddings mapped to same region — useless)
- FLUX head: predicted negative for everything (50.77% accuracy)
- SDXL head: predicted positive for everything (62.75% accuracy)

---

## Every Fix Applied to 75M (all in codebase, pushed to GitHub)

| # | Problem | Fix | File |
|---|---------|-----|------|
| 1 | Only 9 epochs | NUM_EPOCHS = 30 | train_75m.py |
| 2 | Head LR 1e-3 caused collapse | Changed to 1e-4 | train_heads.py |
| 3 | Cosine sim 0.9992 — embedding collapse | Added VICReg loss | train_75m.py |
| 4 | Batch size 64 too small | Changed to 128 | train_75m.py |
| 5 | WARMUP_EPOCHS = 1 too short | Changed to 2 | train_75m.py |
| 6 | Hardcoded /results/ /workspace/ paths | TAR_DIR / CHECKPOINT_DIR env vars | train_75m.py |
| 7 | Missing libraries | Added webdataset, fsspec, soundfile, etc. | requirements.txt |
| 8 | opencv-python (needs headless) | opencv-python-headless | requirements.txt |
| 9 | run.sh / setup.sh were Vast.ai specific | Clean Vultr versions | run.sh, setup.sh |
| 10 | batch_size ignored in heads | All 3 DataLoaders use batch_size param | train_heads.py |

**VICReg details (fix #3 — most important):**
- Variance loss: forces each of 640 dims to have std > 0.5 across a batch
- Covariance loss: forces all 640 dims to be decorrelated
- Constants: WEIGHT=0.1, STD_COEFF=25.0, COV_COEFF=1.0, MIN_STD=0.5
- Runs OUTSIDE autocast in full float32 — bfloat16 causes instability
- Training loss = mae_loss + 0.1 * vicreg_loss
- Second full forward pass per step to get embeddings — intentional

---

## Current Status

| Item | Status |
|------|--------|
| ForensicNet-Nano (5M) | ✅ Complete — images only, proof of concept |
| ForensicNet-75M architecture | ✅ Built and validated |
| ForensicNet-75M all fixes | ✅ Applied and pushed to GitHub |
| ForensicNet-75M training | ⏳ WAITING FOR GPU ACCESS |
| ForensicNet-75M head training | ⏳ After backbone training |
| ForensicNet-300M codebase | ✅ Built (301.4M params verified) |
| ForensicNet-300M training | ⏳ After 75M proves approach works |
| GitHub repo structure | ✅ Clean — forensicnet_75m/ and forensicnet_300m/ |

---

## NEXT ACTION: Train the 75M on GPU

### Plan
- **Phase 1:** ~20 epochs on any available A100 (~$2.40/hr)
- **Phase 2:** Resume for final 10 epochs on DigitalOcean or another provider

### Step 1 — When you have GPU access, connect and verify:
```bash
nvidia-smi
```
Must show GPU model and CUDA version.

### Step 2 — Clone and setup:
```bash
git clone https://github.com/ashkansamali2-rgb/forensicnet
cd forensicnet/forensicnet_75m
bash setup.sh
export HF_TOKEN="your_actual_token_here"
```

### Step 3 — Verify PyTorch sees GPU:
```bash
python3 -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

### Step 4 — Verify model builds:
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from models.backbone_75m import ForensicNet75M
from models.decoder_75m import MAEDecoder75M
m = ForensicNet75M()
bp = sum(p.numel() for p in m.parameters())
print(f'Backbone: {bp/1e6:.1f}M')
assert 65_000_000 < bp < 90_000_000
print('PASS')
"
```

### Step 5 — Start training:
```bash
screen -S training
bash run.sh
```
Detach: Ctrl+A then D. Reconnect: `screen -r training`

### Step 6 — Monitor:
```bash
watch -n 5 nvidia-smi

watch -n 60 "python3 -c \"
import json
with open('checkpoints_75m/training_log.json') as f:
    log = json.load(f)
for e in log:
    print(f'Epoch {e[\"epoch\"]}: loss={e[\"train_loss\"]:.5f} gate={e[\"gate_mean\"]:.3f}')
\""
```

### Resume if interrupted:
```bash
export RESUME_CHECKPOINT=./checkpoints_75m/backbone_75m_best.pt
export START_EPOCH=X
export END_EPOCH=30
bash run.sh
```

---

## Healthy Training Targets

| Epoch | MAE Loss | Gate | VICReg Loss |
|-------|----------|------|-------------|
| 0 | 0.75–0.85 | 0.45–0.55 | 0.5–2.0 |
| 5 | < 0.65 | 0.35–0.65 | < 0.5 |
| 10 | < 0.55 | 0.3–0.7 | < 0.3 |
| 20 | < 0.45 | 0.3–0.8 | < 0.2 |
| 30 | < 0.40 | 0.3–0.8 | < 0.15 |

**Key target: cosine similarity < 0.92 after training (was 0.9992)**

**Red flags — stop and tell Claude:**
- Loss goes NaN
- Loss flat for 5+ consecutive epochs
- Gate collapses to <0.1 or >0.99
- GPU utilisation <50%
- VICReg loss goes NaN

---

## After Training — Diagnostics

```bash
scp root@server-ip:~/forensicnet/forensicnet_75m/checkpoints_75m/backbone_75m_best.pt ~/Desktop/
python3 test_backbone.py --checkpoint ~/Desktop/backbone_75m_best.pt
```

Pass criteria:
- 10/10 tests pass
- Cosine similarity < 0.92 (critical)
- Gate mean: 0.3–0.8

---

## Head Training (after diagnostics pass)

```bash
python3 train_heads.py \
    --backbone ~/Desktop/backbone_75m_best.pt \
    --hf-token your_token \
    --output-dir ./heads \
    --epochs 20 \
    --batch-size 64
```

Expected: FLUX and SDXL accuracy > 85%, FPR < 10%.

---

## 300M Training Plan (after 75M heads work)

```
forensicnet/forensicnet_300m/
```

- Hardware: 8x B200 GPUs (not yet available)
- 25 epochs, 800K samples, batch 32 per GPU (256 effective)
- All same fixes as 75M already applied
- run.sh already configured for --nproc_per_node=8
- Budget estimate: ~€300-400

Do NOT start 300M until 75M heads achieve > 85% accuracy.

---

## Technical Decisions — Never Reverse

1. torch.scatter in decoder (not gather) — gradient flow fix
2. Dropout 0.1 backbone, 0.0 decoder — higher caused mode collapse
3. Input [3,128,128], patch size 4, 1024 patches — never change
4. No spatial interpolation on frequency data — destroys forensic info
5. Z-score normalise before GatedRepresentation — prevents gate collapse
6. Two branches only (Visual + Audio) — image and video share visual branch
7. bfloat16 mixed precision — no GradScaler needed
8. Backbone on REAL data only — heads handle real vs AI
9. VICReg in float32 — bfloat16 causes covariance instability
10. Video pipeline unchanged — slow but correct, do not modify

---

## How to Continue in a New Chat

"I am continuing a deepfake detection project called ForensicNet/Cantivia.
I am a secondary school student in Ireland building this for YSTE.
I use Claude Code for all code changes — give me Claude Code prompts, not raw code.
My GitHub repo is ashkansamali2-rgb/forensicnet (branch: main).
Local path: /Users/ashkansamali/Vision/backbone/ForensicNet
Python env: /Users/ashkansamali/forensicnet_env/bin/python3
Here is my full project context: [paste this entire document]"
