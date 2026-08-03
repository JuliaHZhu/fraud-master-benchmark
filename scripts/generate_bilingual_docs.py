#!/usr/bin/env python3
"""
Generate bilingual (Classical Chinese + Vernacular) docs for 《骗经》cases.
Reads pianjing_all_88.json and produces Markdown files under docs/bilingual/.
"""
import json
import os
import re
from pathlib import Path

# Modern fraud mapping for each class
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


def split_body(body: str):
    """Split case body into main story and '按' commentary."""
    # Some cases use 按： some use 吾观... or nothing
    if "\n\n按：" in body:
        parts = body.split("\n\n按：", 1)
        return parts[0].strip(), "按：" + parts[1].strip()
    if "\n\n吾观" in body:
        parts = body.split("\n\n吾观", 1)
        return parts[0].strip(), "吾观" + parts[1].strip()
    if "\n\n按：" in body:
        parts = body.split("\n\n按：", 1)
        return parts[0].strip(), "按：" + parts[1].strip()
    # fallback: last paragraph starting with commentary markers
    lines = body.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("按：") or lines[i].startswith("吾观") or lines[i].startswith("按:"):
            story = "\n".join(lines[:i]).strip()
            comment = "\n".join(lines[i:]).strip()
            return story, comment
    return body.strip(), ""


def extract_entities(story: str):
    """Naive entity extraction for summary scaffolding."""
    names = []
    # 姓X名Y者
    for m in re.finditer(r'有姓(\S)名(\S)(?:者|，)', story):
        names.append(m.group(1) + m.group(2))
    # X姓Y名
    for m in re.finditer(r'(\S)姓(\S)名(\S)', story):
        names.append(m.group(2) + m.group(3))
    # 开头 "某处人某某者"
    m = re.search(r'^(?:\S{2,6}人)?(\S{2,4})者，', story)
    if m:
        names.append(m.group(1))
    # victim/profession hints
    profs = re.findall(r'(贩[马布猪]|客商|店主|举子|监生|裁缝|秀才|士子|牙人|棍)', story)
    places = re.findall(r'(\S{1,4}府|\S{1,4}县|\S{1,4}州|\S{1,4}街|\S{1,4}寺|\S{1,4}门)', story)
    return list(set(names)), list(set(profs)), list(set(places))


def simple_summary(title: str, story: str, names, profs, places):
    """Generate a very rough vernacular gist."""
    lines = []
    # Clean names/places to avoid dumping full text
    clean_names = [n for n in names if 2 <= len(n) <= 4 and n not in story[:20]]
    clean_places = [p for p in places if 2 <= len(p) <= 6]
    who = "、".join(clean_names[:2]) if clean_names else "某商旅"
    where = "、".join(clean_places[:2]) if clean_places else "某地"
    what = profs[0] if profs else "商旅"
    lines.append(f"**人物**：{who}（{what}）")
    lines.append(f"**地点**：{where}")
    # First sentence as premise, capped
    first_sent = story.split("。")[0] + "。"
    if len(first_sent) > 100:
        first_sent = first_sent[:100] + "……"
    lines.append(f"**起因**：{first_sent}")
    # Trick keyword detection
    tricks = []
    if "假" in title or "假" in story[:200]:
        tricks.append("假冒身份")
    if "换" in title or "调包" in story or "替包" in story:
        tricks.append("调包")
    if "寄" in story[:200] and "银" in story[:200]:
        tricks.append("寄存财物")
    if "赌" in title or "赌" in story[:200]:
        tricks.append("诱赌")
    if "酒" in story[:200] and "色" in story[:200]:
        tricks.append("酒色引诱")
    if "奸" in title:
        tricks.append("奸情设局")
    if "船" in title or "舵" in story[:200]:
        tricks.append("旅途设局")
    if "银" in title and ("假" in title or "换" in title):
        tricks.append("假币/调银")
    if not tricks:
        tricks.append("言语诱骗")
    lines.append(f"**手法**：{'、'.join(tricks)}")
    # Outcome from last sentence, capped
    last_sents = [s for s in story.split("。") if s.strip()][-2:]
    outcome = last_sents[-1][-60:] + "。" if last_sents else "未知"
    if len(outcome) > 80:
        outcome = outcome[-80:]
    lines.append(f"**结果**：……{outcome}")
    return "\n".join(lines)


def generate_case_md(item, idx: int):
    """Generate markdown for a single case."""
    cls = item["class"]
    title = item["title"]
    body = item["body"]
    story, comment = split_body(body)
    names, profs, places = extract_entities(story)
    modern_name, modern_desc = CLASS_MAPPING.get(cls, ("其他诈骗", "暂无映射"))

    md = f"""### {idx+1}. {title}

> **所属类别**：{cls}  
> **现代映射**：{modern_name} — {modern_desc}

---

#### 原文

{story}

"""
    if comment:
        md += f"""#### 作者点评

{comment}

"""
    md += f"""#### 白话梗概

{simple_summary(title, story, names, profs, places)}

#### 防骗要点

- 识破关键词：`{title}` 的核心在于利用受害者的 **贪心 / 轻信 / 面子 / 恐惧** 之一。
- 现代变种：此类手法在当代演变为 **{modern_name}**，底层心理机制完全一致。
- 应对原则：遇事先验证身份与实物，不贪图意外之财，不被紧急情绪裹挟。

---

"""
    return md


def main():
    root = Path(__file__).parent.parent
    # Try workspace root first (flat format: list of {class, title, body})
    json_path = Path("/home/ubuntu/.nanobot/workspace/pianjing_all_88.json")
    if not json_path.exists():
        json_path = root / "datasets" / "pianjing_parsed.json"
    if not json_path.exists():
        print("Cannot find pianjing_all_88.json or pianjing_parsed.json")
        return

    out_dir = root / "docs" / "bilingual"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    # Normalize: flat list vs nested {class, stories}[]
    data = []
    if isinstance(raw, list) and raw:
        if "stories" in raw[0]:
            # nested format from pianjing_parsed.json
            for group in raw:
                c = group["class"].replace("一类　", "").replace("二类　", "").replace("三类　", "").replace("四类　", "").replace("五类　", "").replace("六类　", "").replace("七类　", "").replace("八类　", "").replace("九类　", "").replace("十类　", "").replace("十一类　", "").replace("十二类　", "").replace("十三类　", "").replace("十四类　", "").replace("十五类　", "").replace("十六类　", "").replace("十七类　", "").replace("十八类　", "").replace("十九类　", "").replace("二十类　", "").replace("二十一类　", "").replace("二十二类　", "").replace("二十三类　", "").replace("二十四类　", "").strip()
                for story in group["stories"]:
                    data.append({"class": c, "title": story["title"], "body": story["body"]})
        else:
            data = raw

    # Group by class
    by_class = {}
    for item in data:
        c = item["class"]
        by_class.setdefault(c, []).append(item)

    # Generate per-class files
    index_links = []
    for cls, items in sorted(by_class.items(), key=lambda x: -len(x[1])):
        safe_name = re.sub(r'[\\/:*?"<>|()]', '', cls)
        filename = f"{safe_name}.md"
        filepath = out_dir / filename
        modern_name, modern_desc = CLASS_MAPPING.get(cls, ("其他诈骗", "暂无映射"))

        content = f"""# {cls}（共 {len(items)} 则）

> **现代映射**：{modern_name}  
> **特征概述**：{modern_desc}

---

"""
        for i, item in enumerate(items):
            content += generate_case_md(item, i)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Generated {filepath}")
        index_links.append(f"- [{cls}（{len(items)} 则）](bilingual/{filename})")

    # Generate index
    index_path = root / "docs" / "README.md"
    index_content = f"""# 《骗经》文白对照与讲解

本目录提供明代张应俞《骗经》24 类 {len(data)} 则案例的结构化文白对照文档。

每则案例包含：
1. **原文** — 保留明代白话原貌
2. **作者点评** — 张应俞的"按"或"吾观"评论
3. **白话梗概** — 情节、人物、手法、结果的现代语言梳理
4. **防骗要点** — 提炼底层心理机制与现代变种

## 目录

{chr(10).join(index_links)}

---

## 设计说明

- 原文未做现代汉语逐字翻译，保留历史语感；白话梗概提供情节骨架。
- "现代映射"将明代骗术与当代诈骗类型对应，揭示**底层心理机制的跨时代稳定性**。
- 建议配合 [PJ-Fraud-Bench 数据集](../datasets/) 使用，作为中文诈骗识别模型的训练/评测语料。

## 引用

> 张应俞《骗经》（明代）  
> 本项目整理：PJ-Fraud-Bench
"""
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_content)
    print(f"Generated {index_path}")


if __name__ == "__main__":
    main()
