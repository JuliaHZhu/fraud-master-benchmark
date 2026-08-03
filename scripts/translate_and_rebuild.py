#!/usr/bin/env python3
"""
Translate 《骗经》cases paragraph-by-paragraph using local API.
Reads pianjing_all_88.json, calls local LLM for vernacular translation,
outputs rich bilingual markdown to docs/bilingual/.
"""
import json
import os
import re
import time
from pathlib import Path

# Try to use OpenAI client; fallback to requests
API_KEY = "sk-qvRSm6G8ZPESJ62fW2MOr8Wp4Dfy2Pn70iFB5nVXOZyyERLK"
API_BASE = "http://127.0.0.1:9999/v1"
MODEL = "moonshot-v1-128k"

client = None

def _init_client():
    global client
    if client is not None:
        return client
    try:
        from openai import OpenAI
        client = OpenAI(api_key=API_KEY, base_url=API_BASE)
        return client
    except Exception:
        import requests
        class FakeClient:
            def chat_completions_create(self, **kwargs):
                url = f"{API_BASE}/chat/completions"
                headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
                resp = requests.post(url, headers=headers, json=kwargs, timeout=120)
                resp.raise_for_status()
                return resp.json()
        client = FakeClient()
        return client

def translate_chunk(text: str, retry: int = 2) -> str:
    """Translate a chunk of Ming vernacular into modern Chinese."""
    c = _init_client()
    prompt = (
        "请将以下明代白话小说段落翻译为现代汉语白话文。"
        "要求：1.准确传达原意，语言自然通顺；"
        "2.人名、地名、官职保留；3.对话保留双引号；"
        "4.不要输出任何解释、注释、前缀，只输出翻译后的正文。\n\n"
        f"原文：\n{text}\n\n白话译文："
    )
    for attempt in range(retry + 1):
        try:
            if hasattr(c, "chat"):
                resp = c.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=2048,
                )
                return resp.choices[0].message.content.strip()
            else:
                raw = c.chat_completions_create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=2048,
                )
                return raw["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt < retry:
                time.sleep(2)
                continue
            print(f"  Translation failed after {retry+1} attempts: {e}")
            return "[翻译失败，请稍后重试]"


def split_paragraphs(body: str):
    """Split body into story paragraphs + commentary."""
    # Find commentary start
    comment_start = -1
    markers = ["\n\n按：", "\n\n按:", "\n\n吾观"]
    for mk in markers:
        idx = body.find(mk)
        if idx != -1:
            comment_start = idx
            break
    if comment_start != -1:
        story = body[:comment_start].strip()
        comment = body[comment_start:].strip()
    else:
        story = body.strip()
        comment = ""
    # Split story into natural paragraphs (double newline or sentence clusters)
    story_paras = [p.strip() for p in re.split(r'\n\n+', story) if p.strip()]
    return story_paras, comment


def build_case_md(idx: int, title: str, cls: str, story_paras: list, comment: str, modern_name: str, modern_desc: str):
    md = f"""### {idx}. {title}

> **所属类别**：{cls}  
> **现代映射**：{modern_name} — {modern_desc}

---

"""
    # Story paragraphs with translation
    for p in story_paras:
        translated = translate_chunk(p)
        md += f"**原文**\n\n{p}\n\n**译文**\n\n{translated}\n\n"
        time.sleep(0.5)  # rate limit safety

    if comment:
        translated_comment = translate_chunk(comment)
        md += f"**作者点评（原文）**\n\n{comment}\n\n**作者点评（译文）**\n\n{translated_comment}\n\n"
        time.sleep(0.5)

    md += f"""---

#### 防骗要点

- **核心机制**：`{title}` 利用的是受害者的 **贪心 / 轻信 / 面子 / 恐惧** 之一。
- **现代变种**：此类手法在当代演变为 **{modern_name}**。
- **应对原则**：遇事先验证身份与实物，不贪图意外之财，不被紧急情绪裹挟。

---

"""
    return md


def main():
    root = Path("/home/ubuntu/.nanobot/workspace/fraud-master-benchmark")
    json_path = Path("/home/ubuntu/.nanobot/workspace/pianjing_all_88.json")
    out_dir = root / "docs" / "bilingual"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    data = raw if isinstance(raw, list) and "stories" not in raw[0] else []
    if not data and isinstance(raw, list):
        for group in raw:
            c = re.sub(r'^(一|二|三|四|五|六|七|八|九|十|十一|十二|十三|十四|十五|十六|十七|十八|十九|二十|二十一|二十二|二十三|二十四)类\s*', '', group["class"]).strip()
            for story in group.get("stories", []):
                data.append({"class": c, "title": story["title"], "body": story["body"]})

    CLASS_MAPPING = {
        "脱剥骗": ("资产剥离/借用名义诈骗", "利用他人身份或物品作为掩护骗取财物，如假道灭虢、借屋脱布、明窃等"),
        "丢包骗": ("拾遗诈骗 / 路捡分赃", "故意丢包引诱路人，再以分赃为由调包或骗取财物"),
        "换银骗": ("假币/调包诈骗", "以假银、假金或调包手法骗取真钱"),
        "诈哄骗": ("信息诈骗 / 心理操控", "利用虚假信息、梦境、迷信等手段恐吓或哄骗受害者掏钱"),
        "伪交骗": ("社交工程 / 熟人杀猪盘", "伪装亲近关系，长期布局，诱使受害者沉迷酒色或陷入官司，最终侵吞财产"),
        "牙行骗": ("中介诈骗 / 货代卷款", "牙行（中介）骗取客商货物，以后货抵前债，或以女抵债等"),
        "引赌骗": ("赌博诈骗 / 杀猪盘", "引诱受害者赌博，设局骗取钱财"),
        "露财骗": ("炫富引诱 / 抢劫前置", "故意显露财富引诱贪心者上当，再行抢劫或诈骗"),
        "谋财骗盗": ("谋财害命 / 黑吃黑", "以计谋骗取或盗窃他人财物，常伴随暴力或谋害"),
        "盗劫骗": ("盗窃抢劫", "直接以盗窃、抢劫手段获取财物"),
        "强抢骗": ("暴力抢夺 / 路霸", "公开使用暴力或威胁抢夺财物"),
        "在船骗": ("旅途诈骗 / 交通工具犯罪", "利用船舱封闭环境，对旅客实施诈骗、盗窃或谋害"),
        "诗词骗": ("文艺诈骗 / 雅骗", "以诗文、风雅为幌子，骗取钱财或女色"),
        "假银骗": ("假币诈骗", "使用假银、假钞等骗取真币或货物"),
        "衙役骗": ("公权力诈骗 / 冒充公检法", "冒充或利用衙门差役身份实施诈骗"),
        "婚娶骗": ("婚恋诈骗 / 彩礼诈骗", "以婚嫁为名骗取彩礼、财物或人口"),
        "奸情骗": ("色诱诈骗 / 仙人跳", "利用奸情、色诱设局，敲诈勒索或骗取财产"),
        "妇人骗": ("女骗子系列", "女性以美色、伪装的柔弱或亲缘关系行骗"),
        "拐带骗": ("拐卖人口", "诱拐人口贩卖或勒赎"),
        "买学骗": ("教育诈骗 / 学位买卖", "以买取功名、学位为名骗取钱财"),
        "僧道骗": ("宗教诈骗 / 假冒出家人", "冒充僧道以化缘、祈福、消灾等名义骗钱"),
        "炼丹骗": ("投资诈骗 / 虚假项目", "以炼丹、炼金等虚假技术项目骗取投资"),
        "法术骗": ("迷信诈骗 / 神棍", "以法术、符咒、驱邪等迷信手段骗取钱财"),
        "引嫖骗（附引嫖类）": ("色情引诱诈骗", "以嫖娼为诱饵，实施抢劫、敲诈或诈骗"),
    }

    # Group by class
    by_class = {}
    for item in data:
        by_class.setdefault(item["class"], []).append(item)

    total_cases = sum(len(v) for v in by_class.values())
    processed = 0

    for cls, items in sorted(by_class.items(), key=lambda x: -len(x[1])):
        safe_name = re.sub(r'[\\/:*?"<>|()]', '', cls)
        filepath = out_dir / f"{safe_name}.md"
        modern_name, modern_desc = CLASS_MAPPING.get(cls, ("其他诈骗", "暂无映射"))

        content = f"""# {cls}（共 {len(items)} 则）

> **现代映射**：{modern_name}  
> **特征概述**：{modern_desc}

---

"""
        for i, item in enumerate(items, 1):
            processed += 1
            print(f"[{processed}/{total_cases}] Translating: {item['title']} ({cls})")
            story_paras, comment = split_paragraphs(item["body"])
            content += build_case_md(i, item["title"], cls, story_paras, comment, modern_name, modern_desc)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {filepath}")

    print("\nDone. All bilingual docs rebuilt with translations.")


if __name__ == "__main__":
    main()
