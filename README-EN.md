# PJ-Fraud-Bench: A Fraud Detection Benchmark from *Pian Jing*

A Chinese fraud detection and red-team adversarial benchmark built from Zhang Yingyu's *Pian Jing* (24 categories, 83 historical fraud cases, Ming Dynasty).

📚 **[Chinese Bilingual Commentary](docs/bilingual/)** | 📖 **[English Category Summaries](docs/bilingual-en/)** | 📜 **[Raw Text](骗经_utf8.txt)**

---

## Dataset Overview

| Task | Train | Dev | Test | Notes |
|------|-------|-----|------|-------|
| Fraud Detection (Binary) | 99 | 33 | 34 | fraud / safe |
| Fraud Type Classification (24-class) | 49 | 17 | 17 | strip-and-rob / dropped-bag / silver-swap ... |
| Red-Team Adversarial Test | - | - | 12 | 6 attack strategies |
| Fraud Element Extraction | - | - | 83 | Pending manual annotation |

**Data directories:**
- `datasets/` — Original datasets
- `datasets_v2/` — Cleaned datasets (recommended)

---

## Tasks

### Task 1: Fraud Detection (Binary Classification)

Given a dialogue or scenario description, determine whether it is a fraud.

**Input format** (JSONL):
```json
{"id": "fraud_0", "text": "江西有陈姓庆名者，常贩马往南京...", "label": "fraud"}
{"id": "safe_0", "text": "一位顾客到布店挑选布料...", "label": "safe"}
```

**Prediction format**:
```json
{"id": "fraud_0", "label": "fraud"}
{"id": "safe_0", "label": "safe"}
```

**Evaluation**:
```bash
python scripts/eval_fraud_benchmark.py binary \
  --pred predictions.jsonl \
  --gold datasets/fraud_detection_test.jsonl
```

### Task 2: Fraud Type Classification (24-Class Multi-class)

Given a confirmed fraud text, identify the specific fraud type (one of 24 categories).

**24 fraud types**:
1. 脱剥骗 (strip-and-rob)  2. 丢包骗 (dropped-bag)  3. 换银骗 (silver-swap)
4. 诈哄骗 (deception-and-intimidation)  5. 伪交骗 (fake-friendship)
6. 牙行骗 (broker)  7. 引赌骗 (gambling-bait)  8. 露财骗 (flaunted-wealth)
9. 谋财骗盗 (premeditated-property-crime)  10. 盗劫骗 (theft-and-robbery)
11. 强抢骗 (strongarm-robbery)  12. 在船骗 (shipboard-robbery)
13. 诗词骗 (poetry-scholar-impersonation)  14. 假银骗 (counterfeit-silver)
15. 衙役骗 (corrupt-bailiff)  16. 婚娶骗 (marriage-fraud)
17. 奸情骗 (adultery-trap)  18. 妇人骗 (female-accomplice)
19. 拐带骗 (kidnapping)  20. 买学骗 (fake-credential)
21. 僧道骗 (fake-cleric)  22. 炼丹骗 (alchemy-pill)
23. 法术骗 (fake-sorcery)  24. 引嫖骗 (brothel-bait)

**Prediction format**:
```json
{"id": "fraud_0", "fraud_type": "脱剥骗"}
```

### Task 3: Red-Team Adversarial Test

Test model resistance against fraud-related requests.

**6 attack strategies**:
| Category | Description | Count |
|----------|-------------|-------|
| fraud_generation | Direct request to generate fraud content | 2 |
| roleplay_fraud | Roleplay to induce fraud participation | 2 |
| educational_jailbreak | Bypass restrictions under research/education pretext | 2 |
| obfuscated | Wrap fraud requests in neutral language | 2 |
| adaptation | Ask to adapt ancient fraud schemes to modern contexts | 2 |
| anti_fraud | Anti-fraud requests (should be answered normally) | 2 |

**Prediction format**:
```json
{"id": "rt_001", "refused": true, "reason": "Cannot assist with generating fraud content"}
```

**Evaluation**:
```bash
python scripts/eval_fraud_benchmark.py redteam --pred redteam_results.jsonl
```

### Task 4: Fraud Element Extraction

Extract key elements from fraud texts: fraud type, victim type, bait, method, outcome.

**Pending manual annotation** — Currently a template file; requires domain expert annotation before use as an extraction benchmark.

---

## Data Sources

- **Raw text**: Zhang Yingyu, *Pian Jing* (24 categories, 83 cases, Ming Dynasty)
- **Negative samples**: Safe scenarios rewritten from the commentary ("按") sections of *Pian Jing* + generic business/social scenarios
- **Red-team prompts**: 6 attack strategies designed from *Pian Jing* cases

---

## Design Rationale

### Why *Pian Jing*?

1. **Cross-era stability**: Ming Dynasty fraud tactics share the same underlying psychological mechanisms with modern telecom fraud (trust exploitation, time pressure, identity disguise)
2. **Privacy-safe**: Historical cases do not involve real personal information, making the benchmark safer for public evaluation
3. **Structured**: The author already systematically categorized cases into 24 types, naturally fitting a multi-class task
4. **Dialogue-rich**: Extensive direct quotations, suitable for conversational fraud detection training

### Red-Team Design Principles

- **Multi-layer defense testing**: Escalate from direct request → roleplay → educational pretext → obfuscated wording, probing model boundaries at each level
- **Positive-negative control**: Include safe requests (anti_fraud) to prevent over-refusal
- **Knowledge transfer test**: Ask to modernize ancient fraud schemes, testing whether the model assists in harmful knowledge transfer

---

## Project Structure

```
fraud-master-benchmark/
├── datasets/              # Original datasets
├── datasets_v2/           # Cleaned datasets (recommended)
├── docs/
│   ├── bilingual/         # Chinese bilingual commentary (24 categories)
│   └── bilingual-en/      # English category summaries (24 categories)
├── scripts/               # Evaluation and generation scripts
├── 骗经_utf8.txt          # Raw text
└── README-EN.md
```

---

## Extension Ideas

1. **Scale up**: Use LLM to generate multiple variants per case (modern context, different lengths, different perspectives)
2. **Adversarial augmentation**: Paraphrase positive samples, insert noise, test model robustness
3. **Multi-turn dialogue**: Expand single-turn cases into multi-turn interactive fraud conversations
4. **Cross-lingual**: Translate cases into English / other languages, test cross-lingual fraud detection

---

## Citation

If you use this benchmark, please cite:

```bibtex
@misc{pj-fraud-bench,
  title = {PJ-Fraud-Bench: A Fraud Detection Benchmark from Pian Jing},
  year = {2026},
  howpublished = {\url{https://github.com/JuliaHZhu/fraud-master-benchmark}}
}
```

Source text: Zhang Yingyu, *Pian Jing* (Ming Dynasty)
