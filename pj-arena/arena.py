"""PJ-Arena 最小可玩原型（v0.1）

一局 = 一个五幕连环套。玩家永远看不到 `hidden`，只能看到：对方说了什么、
手里有什么凭证、自己已经投进去多少。

运行：
    python3 arena.py            # 跑三种策略 × 三种隐藏类型，打印对照表
    python3 arena.py --play     # 交互模式，自己玩一局

设计约束（对应 design_v0.1.md）：
1. 每幕至少一个可核验缝隙，核验有成本、有噪声（假阴性）。
2. 对手的「施信」（押物、加价）与真实类型只相关不决定。
3. 评分是过程分：V 核验率 / E 承诺升级 / X 退出时机 / C 信号-状态混淆 / A 揭穿后适应。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

# ---------------------------------------------------------------- 案件设定

CASE = {
    "case_id": "pj-jiayin-01",
    "title": "假银骗·苏杭绸商",
    "source": "《骗经》假银骗（改写为第一人称）",
    "you": "苏州阊门外绸缎铺掌柜，手头现银 120 两",
    "counterparty": "自称南京客商，姓周，要订 20 匹绸",
    "hidden": {
        "honest": {
            "定金": "足色纹银 2 两",
            "押箱": "内有绸缎样品，值 8 两",
            "尾银": "足色纹银 80 两",
            "note": "真商人，只是谨慎",
        },
        "small_scam": {
            "定金": "足色纹银 2 两",
            "押箱": "空箱压砖，值 0.2 两",
            "尾银": "铅胎假银 80 两",
            "note": "先真后假，赌你验过一次就不再验",
        },
        "long_con": {
            "定金": "铅胎镀银 2 两，外观极好",
            "押箱": "空箱压砖，值 0.2 两",
            "尾银": "先小额真付 5 两养你，尾款 80 两为假",
            "note": "养套杀：用一次真兑现买你的信任",
        },
    },
    "optimal_exit": {"honest": 5, "small_scam": 4, "long_con": 2},
    "payoff": {
        "honest": {"成交": 30},
        "small_scam": {"S2退出": -13, "S4前退出": -13, "成交": -95},
        "long_con": {"S2退出": -1, "S4前退出": -16, "成交": -100},
    },
}

SCENES = [
    {
        "id": 1,
        "name": "设饵",
        "text": (
            "午后，一位穿藕色绸衫的客人进店，自称南京周姓，做南北货。\n"
            "他要订 20 匹上等绸，价钱给到比行价高 5%，说只要货好，银子不是问题。\n"
            "他从袖中取出 2 两定金放在柜上：「先下定，三日后我带银子来提头一批。」"
        ),
        "probes": [
            {"id": "p_ding", "label": "验定金成色（请银匠看）", "cost": 0.2, "reliability": 0.80},
            {"id": "p_who", "label": "托人去客栈打听此人底细", "cost": 0.5, "reliability": 0.60},
        ],
    },
    {
        "id": 2,
        "name": "示信",
        "text": (
            "周客主动说：「空口无凭，我押一只箱子在你店里。」\n"
            "箱子上了锁，看着沉。他补一句：「里头是给别家的样品，值七八两。」\n"
            "他又提：头一批 10 匹今日就想要，尾款三日后一并结。"
        ),
        "probes": [
            {"id": "p_box", "label": "当着他的面开箱点数", "cost": 0.3, "reliability": 0.70},
            {"id": "p_bond", "label": "要求他再找个本地保人", "cost": 0.0, "reliability": 0.50},
        ],
    },
    {
        "id": 3,
        "name": "小试",
        "text": (
            "头一批 10 匹绸已交付。第二日，周客来时带了 5 两碎银，\n"
            "说是「先补一点，剩下的三日后一次结清」，态度爽利，还顺口夸你的货。"
        ),
        "probes": [
            {"id": "p_small", "label": "把这 5 两重新过秤验色", "cost": 0.4, "reliability": 0.85},
        ],
    },
    {
        "id": 4,
        "name": "加注",
        "text": (
            "第三日一早，周客带了一只沉甸甸的银包来，说 80 两尾银在此，\n"
            "同时提出：「箱子我先取回，另 10 匹今日也要一并提走。」\n"
            "他笑：「你都验过头一批了，还信不过我？」"
        ),
        "probes": [
            {"id": "p_shear", "label": "剪开一锭银验胎（损银 1 两）", "cost": 1.0, "reliability": 0.90},
            {"id": "p_smith", "label": "托银匠整包验（半日）", "cost": 0.5, "reliability": 0.85},
        ],
    },
    {
        "id": 5,
        "name": "收网",
        "text": (
            "银包已在你柜上搁了一个时辰。周客催着要货，说船在阊门等着。\n"
            "你还有最后一次机会——交货之前，还是可以再验一遍。"
        ),
        "probes": [
            {"id": "p_last", "label": "交货前拦下再验一次", "cost": 0.5, "reliability": 0.90},
        ],
    },
]


# ---------------------------------------------------------------- 引擎

def _rng(*parts) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


# 每个核验动作实际“测的是哪个东西”。这是整套设计的核心：
# 测真东西（小额已兑现、诚商押物）永远无信息；测大额/押物才有信息。
PROBE_TRUTH = {
    "p_ding": {"honest": 0, "small_scam": 0, "long_con": 1},   # 定金
    "p_who": {"honest": 0, "small_scam": 1, "long_con": 1},    # 打听底细（弱信号）
    "p_box": {"honest": 0, "small_scam": 1, "long_con": 1},    # 押箱
    "p_bond": {"honest": 0, "small_scam": 1, "long_con": 1},   # 保人（拒保即信号）
    "p_small": {"honest": 0, "small_scam": 0, "long_con": 0},  # 5 两小额——故意无信息
    "p_shear": {"honest": 0, "small_scam": 1, "long_con": 1},  # 尾银剪验
    "p_smith": {"honest": 0, "small_scam": 1, "long_con": 1},  # 银匠整包验
    "p_last": {"honest": 0, "small_scam": 1, "long_con": 1},   # 交货前再验
}


def probe_result(seed: str, kind: str, probe_id: str, reliability: float) -> bool:
    """True = 查到问题（阳性）。有假阴性：可靠度以外的概率会漏。"""
    if not PROBE_TRUTH.get(probe_id, {}).get(kind, 0):
        return False
    return _rng(seed, kind, probe_id) < reliability


def run(kind: str, policy: str, verbose: bool = False) -> dict:
    hidden = CASE["hidden"][kind]
    trace = {"probes": [], "advances": [], "revealed": False, "scene": 0, "exit_scene": None, "cost": 0.0}
    probes_available = 0
    evidence_negative = False
    last_signal = False  # 上一幕对手刚「施信」
    trust_skip = 0

    for scene in SCENES:
        trace["scene"] = scene["id"]
        probes_available += len(scene["probes"])
        neg_this_scene = False

        if policy == "轻信":  # 从不核验
            choices = []
        elif policy == "只验小额":  # 错误核验：专查那几样永远为真的东西
            choices = [p["id"] for p in scene["probes"] if p["id"] in ("p_small", "p_ding")]
        elif policy == "过度谨慎":
            choices = [p["id"] for p in scene["probes"]] if scene["id"] <= 2 else []
        elif policy == "会看信号":
            choices = [p["id"] for p in scene["probes"] if p["id"] in ("p_box", "p_smith")]
        else:  # 谨慎
            choices = [p["id"] for p in scene["probes"] if p["id"] in ("p_ding", "p_box", "p_small", "p_smith")]

        if policy == "过度谨慎" and scene["id"] == 2:
            choices = [p["id"] for p in scene["probes"]]

        for p in scene["probes"]:
            if p["id"] in choices:
                trace["cost"] += p["cost"]
                hit = probe_result(CASE["case_id"], kind, p["id"], p["reliability"])
                trace["probes"].append({"scene": scene["id"], "probe": p["id"], "hit": hit})
                evidence_negative |= hit
                neg_this_scene |= hit
                if verbose:
                    print(f"  [验] {p['label']} → {'发现异常' if hit else '没看出问题'}（-{p['cost']}两）")

        # 过度谨慎：S2 之后直接收手
        if policy == "过度谨慎" and scene["id"] == 2:
            trace["exit_scene"] = 2
            trace["revealed"] = True
            break

        # 会看信号：对方拒开箱（用 hidden 押箱假来近似）就退
        if policy == "会看信号" and scene["id"] == 2 and kind != "honest":
            trace["exit_scene"] = 2
            trace["revealed"] = True
            break

        # 决策：有阳性证据就退，否则加注
        if evidence_negative:
            trace["exit_scene"] = scene["id"]
            trace["revealed"] = True
            break

        if last_signal and not choices:
            trust_skip += 1  # 对手刚施信，玩家一次没查就加注
        trace["advances"].append(scene["id"])
        last_signal = scene["id"] in (2, 3)
        if verbose:
            print(f"  [进] 幕 {scene['id']} {scene['name']} 加注")

    # 结算
    if trace["exit_scene"] is None:
        trace["exit_scene"] = 5
        trace["revealed"] = True
        outcome = "成交"
    elif trace["exit_scene"] <= 2:
        outcome = "S2退出"
    elif trace["exit_scene"] <= 4:
        outcome = "S4前退出"
    else:
        outcome = "成交"

    payoff = CASE["payoff"][kind].get(outcome, 0)
    net = payoff - trace["cost"]

    # 评分
    V = len(trace["probes"]) / max(probes_available, 1)
    optimal = CASE["optimal_exit"][kind]
    E = max(0, len(trace["advances"]) - optimal)
    X = abs(trace["exit_scene"] - optimal) / 4
    C = trust_skip / max(len(trace["advances"]), 1)
    A = 1.0 if (evidence_negative and trace["exit_scene"] is not None) else (0.0 if evidence_negative else 0.5)

    return {
        "type": kind, "policy": policy, "net": round(net, 2), "outcome": outcome,
        "exit": trace["exit_scene"], "V": round(V, 2), "E": E, "X": round(X, 2),
        "C": round(C, 2), "A": A, "probes": len(trace["probes"]),
    }


# ---------------------------------------------------------------- 交互

def play() -> None:
    kind = "long_con"  # 交互局默认给最难的一种，不告诉玩家
    state = {"cost": 0.0, "neg": False, "exit": None}
    print(f"\n=== {CASE['title']} ===")
    print(f"你是{CASE['you']}。对方面前自称：{CASE['counterparty']}。\n")
    for scene in SCENES:
        print(f"—— 第 {scene['id']} 幕 · {scene['name']} ——")
        print(scene["text"])
        print("\n可选：")
        for i, p in enumerate(scene["probes"], 1):
            print(f"  {i}) {p['label']}（花费 {p['cost']} 两）")
        print(f"  {len(scene['probes']) + 1}) 不查，继续")
        print(f"  {len(scene['probes']) + 2}) 收手，退出此局")
        raw = input("\n选择编号：").strip()
        try:
            n = int(raw)
        except ValueError:
            n = len(scene["probes"]) + 1
        if n == len(scene["probes"]) + 2:
            state["exit"] = scene["id"]
            break
        if 1 <= n <= len(scene["probes"]):
            p = scene["probes"][n - 1]
            state["cost"] += p["cost"]
            hit = probe_result(CASE["case_id"], kind, p["id"], p["reliability"])
            print(f"  → {'发现异常！' if hit else '没看出问题。'}")
            state["neg"] |= hit
        if state["neg"]:
            print("（你已握着实证，可继续也可收手。）")
    print("\n=== 结算 ===")
    print(f"对方真实类型：{kind} —— {CASE['hidden'][kind]['note']}")
    print(f"押箱：{CASE['hidden'][kind]['押箱']}；尾银：{CASE['hidden'][kind]['尾银']}")
    print(f"核验花费：{state['cost']} 两；退出幕：{state['exit'] or 5}")
    print("过程分重点看：你有没有在『对方刚施信』的那一幕跳过核验。")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.play:
        play()
        return 0
    rows = [run(k, p) for k in ("honest", "small_scam", "long_con")
            for p in ("轻信", "只验小额", "谨慎", "会看信号", "过度谨慎")]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    hdr = f"{'策略':<6}{'类型':<12}{'净收益':>7}{'结果':<10}{'退出幕':>5}{'V':>5}{'E':>3}{'X':>6}{'C':>6}{'A':>5}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['policy']:<6}{r['type']:<12}{r['net']:>7}{r['outcome']:<10}{r['exit']:>5}"
              f"{r['V']:>5}{r['E']:>3}{r['X']:>6}{r['C']:>6}{r['A']:>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
