"""PJ-Arena v0.2 —— 五幕连环套评估器（12 局）

设计要点见 design_v0.1.md。本文件只做三件事：
1. 把 12 个 case.json 跑成可玩的幕序列（人看叙事，AI 看 JSON）；
2. 用同一套过程分给「策略 × 隐藏类型」打分；
3. 汇总，供人机对照。

用法：
    python3 arena.py                     # 全部 12 局 × 3 类型 × 5 策略，汇总
    python3 arena.py --case pj-03-huanyin --detail
    python3 arena.py --play pj-03-huanyin
    python3 arena.py --json > result.json
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASE_DIR = os.path.join(HERE, "cases")


# ---------------------------------------------------------------- 载入

def load_cases(path: str = CASE_DIR) -> list[dict]:
    out = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            out.append(json.load(fh))
    if not out:
        raise SystemExit(f"no cases found under {path}")
    return out


# ---------------------------------------------------------------- 随机与探针

def _u(*parts) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def probe_hit(case: dict, kind: str, probe: dict) -> bool:
    """True = 查到疑点。两类假信号都在这里：
    - 真有问题但漏检（假阴性）：概率 = 1 - rel
    - 本来没事却报警（假阳性）：false_alarm 表给出概率
    """
    pid = probe["id"]
    truth = case["truth"].get(pid, {}).get(kind, 0)
    if truth:
        return _u(case["case_id"], kind, pid) < probe["rel"]
    fa = case.get("false_alarm", {}).get(pid, {}).get(kind, 0.0)
    return _u(case["case_id"], kind, pid, "fa") < fa


# ---------------------------------------------------------------- 策略

def choose(case: dict, scene: dict, policy: str) -> list[str]:
    ps = scene["probes"]
    if policy == "轻信":
        return []
    if policy == "只验便宜":
        return [p["id"] for p in ps if p["cost"] <= 0.2]
    if policy == "会看信号":
        return [p["id"] for p in ps] if scene["id"] == 2 else []
    if policy == "谨慎":
        if scene["id"] in (2, 4, 5):
            return [max(ps, key=lambda p: p["rel"])["id"]] if ps else []
        return []
    if policy == "全验":
        return [p["id"] for p in ps]
    return []


POLICIES = ("轻信", "只验便宜", "会看信号", "谨慎", "全验")


# ---------------------------------------------------------------- 单局

def run_case(case: dict, kind: str, policy: str, verbose: bool = False) -> dict:
    info_ids = {pid for pid, m in case["truth"].items() if m.get(kind)}
    probes_available = 0
    cost = 0.0
    evidence = False
    advances = 0
    trust_skip = 0
    hits = 0
    probes = 0
    informative = 0
    last_signal = False
    exit_scene = None

    for scene in case["scenes"]:
        probes_available += len(scene["probes"])
        picks = choose(case, scene, policy)
        hit_here = False
        for p in scene["probes"]:
            if p["id"] not in picks:
                continue
            cost += p["cost"]
            probes += 1
            informative += 1 if p["id"] in info_ids else 0
            hit = probe_hit(case, kind, p)
            hits += 1 if hit else 0
            evidence |= hit
            hit_here |= hit
            if verbose:
                print(f"  [验] {p['label']} → {'发现疑点' if hit else '没有异常'}（-{p['cost']} 两）")

        if evidence:
            exit_scene = scene["id"]
            if verbose:
                print(f"  [退] 幕 {scene['id']} 收手")
            break

        if last_signal and not picks:
            trust_skip += 1
        advances += 1
        last_signal = scene["id"] in (2, 3)
        if verbose:
            print(f"  [进] 幕 {scene['id']} {scene['name']} 继续")

    if exit_scene is None:
        exit_scene = len(case["scenes"])
    bucket = "early" if exit_scene <= 2 else ("mid" if exit_scene <= 4 else "deal")
    payoff = case["payoff"][kind].get(bucket, 0)
    # 摩擦：对真商人反复查验会伤面子，每多验一次掉 3 两预期收益
    friction = 4 * max(0, probes - 2) if kind == "honest" else 0
    net = round(payoff - cost - friction, 2)

    best = max(case["payoff"][kind].values())
    optimal = case["optimal_exit"][kind]
    V = round(probes / max(probes_available, 1), 3)
    E = max(0, advances - optimal)
    X = round(abs(exit_scene - optimal) / 4, 3)
    C = round(trust_skip / max(advances, 1), 3)
    A = 1.0 if evidence else 0.5
    I = round(informative / max(probes, 1), 3) if probes else 0.0

    return {
        "case": case["case_id"], "category": case["category"], "type": kind, "policy": policy,
        "net": net, "best": best, "regret": round(best - net, 2), "exit": exit_scene,
        "V": V, "E": E, "X": X, "C": C, "A": A, "I": I, "probes": probes, "hits": hits,
    }


# ---------------------------------------------------------------- 汇总

def summarize(rows: list[dict]) -> str:
    lines = []
    lines.append("按策略汇总（12 局均值；regret = 该类型最优收益 - 实际净收益，越小越好）")
    head = f"{'策略':<8}{'净收益':>8}{'regret':>8}{'V核验':>7}{'I命中':>7}{'E升级':>7}{'X时机':>7}{'C混淆':>7}"
    lines.append(head)
    lines.append("-" * len(head))
    for pol in POLICIES:
        rs = [r for r in rows if r["policy"] == pol]
        if not rs:
            continue
        n = len(rs)
        lines.append(
            f"{pol:<8}{sum(r['net'] for r in rs)/n:>8.1f}{sum(r['regret'] for r in rs)/n:>8.1f}"
            f"{sum(r['V'] for r in rs)/n:>7.2f}{sum(r['I'] for r in rs)/n:>7.2f}"
            f"{sum(r['E'] for r in rs)/n:>7.2f}{sum(r['X'] for r in rs)/n:>7.2f}"
            f"{sum(r['C'] for r in rs)/n:>7.2f}"
        )

    lines.append("")
    lines.append("按隐藏类型（所有策略均值）：走到收网 = 未提前收手")
    head2 = f"{'类型':<12}{'净收益':>8}{'被套率':>8}{'V核验':>7}{'I命中':>7}{'E升级':>7}"
    lines.append(head2)
    lines.append("-" * len(head2))
    for kind in ("honest", "small_scam", "long_con"):
        rs = [r for r in rows if r["type"] == kind]
        if not rs:
            continue
        n = len(rs)
        trapped = sum(1 for r in rs if r["exit"] >= 5) / n
        lines.append(
            f"{kind:<12}{sum(r['net'] for r in rs)/n:>8.1f}{trapped:>8.0%}"
            f"{sum(r['V'] for r in rs)/n:>7.2f}{sum(r['I'] for r in rs)/n:>7.2f}"
            f"{sum(r['E'] for r in rs)/n:>7.2f}"
        )

    lines.append("")
    lines.append("按策略 × 类型（净收益）：")
    head3 = f"{'策略':<8}{'honest':>9}{'small_scam':>12}{'long_con':>10}"
    lines.append(head3)
    lines.append("-" * len(head3))
    for pol in POLICIES:
        cells = []
        for kind in ("honest", "small_scam", "long_con"):
            rs = [r["net"] for r in rows if r["policy"] == pol and r["type"] == kind]
            cells.append(sum(rs) / len(rs) if rs else 0)
        lines.append(f"{pol:<8}{cells[0]:>9.1f}{cells[1]:>12.1f}{cells[2]:>10.1f}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 交互

def play(case: dict) -> None:
    kind = "long_con"
    cost = 0.0
    evidence = False
    print(f"\n=== {case['title']}（{case['category']}） ===")
    print(f"你是{case['you']}。")
    print(f"对面：{case['counterparty']}。\n")
    for scene in case["scenes"]:
        print(f"—— 第 {scene['id']} 幕 · {scene['name']} ——")
        print(scene["text"])
        for i, p in enumerate(scene["probes"], 1):
            print(f"  {i}) {p['label']}（{p['cost']} 两）")
        print(f"  {len(scene['probes'])+1}) 不查，继续")
        print(f"  {len(scene['probes'])+2}) 收手退出")
        raw = input("选择：").strip()
        n = int(raw) if raw.isdigit() else len(scene["probes"]) + 1
        if n == len(scene["probes"]) + 2:
            print(f"\n[退出于幕 {scene['id']}]")
            break
        if 1 <= n <= len(scene["probes"]):
            p = scene["probes"][n - 1]
            cost += p["cost"]
            hit = probe_hit(case, kind, p)
            print("  → " + ("发现疑点" if hit else "没有异常"))
            evidence |= hit
        if evidence:
            input("（你已握有疑点，按回车继续）")
    print(f"\n真实类型：{kind} —— {case['types'][kind]['note']}")
    print(f"核验花费 {cost} 两；关键看：对方施信那一幕你有没有跳过核验。")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=CASE_DIR)
    ap.add_argument("--play", metavar="CASE_ID", nargs="?", const="pj-01-tuobo")
    ap.add_argument("--case", help="只跑某一局")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    cases = load_cases(a.cases)
    if a.case:
        cases = [c for c in cases if c["case_id"] == a.case] or cases
    if a.play:
        pick = next((c for c in cases if c["case_id"] == a.play), cases[0])
        play(pick)
        return 0

    rows = [run_case(c, k, p) for c in cases for k in ("honest", "small_scam", "long_con") for p in POLICIES]

    if a.json:
        print(json.dumps({"cases": len(cases), "rows": rows}, ensure_ascii=False, indent=2))
        return 0
    if a.detail:
        head = f"{'case':<16}{'type':<12}{'策略':<8}{'net':>7}{'regret':>7}{'exit':>5}{'V':>6}{'I':>6}{'E':>3}{'X':>6}{'C':>6}"
        print(head)
        print("-" * len(head))
        for r in rows:
            print(f"{r['case']:<16}{r['type']:<12}{r['policy']:<8}{r['net']:>7}{r['regret']:>7}"
                  f"{r['exit']:>5}{r['V']:>6}{r['I']:>6}{r['E']:>3}{r['X']:>6}{r['C']:>6}")
    print(f"\n共 {len(cases)} 局 / {len(rows)} 次对局\n")
    print(summarize(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
