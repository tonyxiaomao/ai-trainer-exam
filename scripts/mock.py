#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模拟试卷：按官方卷的题型/题量/配分/时间随机组卷、渲染、判分。

用法示例：
  python3 mock.py official --level 3                 # 还原官方模拟卷
  python3 mock.py gen --level 3                      # 随机生成一套理论卷
  python3 mock.py gen --level 4 --kind ops           # 随机生成操作技能卷
  python3 mock.py key --paper 20261110-3T-4f2a       # 看这套卷的答案
  python3 mock.py grade --paper 20261110-3T-4f2a --answers "1:√,2:×,3:A"
  python3 mock.py papers                             # 已生成的试卷
"""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
from practice import answer_pairs

PAPERS = os.path.join(lib.RECORDS, "papers")
COMP = os.path.join(lib.DATA, "composition.json")


def comp(level, kind):
    c = lib.load_json(COMP, {})
    try:
        return c[kind][str(level)]
    except KeyError:
        raise SystemExit("data/composition.json 缺少 %s 级 %s 的组卷规则" % (level, kind))


def bank_of(level, kind):
    return lib.load_bank(level) if kind == "theory" else lib.load_ops(level)


# ---------------------------------------------------------------- 渲染
def render_theory(level, sections, time_min, with_answers=False):
    """sections: [{'type','each','ids','total','desc'}]；题号全卷连续，方便作答与判分"""
    b = lib.apply_corrections(lib.load_bank(level))
    score_all = sum(sec.get("total") or sec["each"] * len(sec["ids"]) for sec in sections)
    n_all = sum(len(sec["ids"]) for sec in sections)
    out = ["# 人工智能训练师（%s级）理论知识试卷" % ("三" if level == "3" else "四"), "",
           "## 注　意　事　项", "",
           "1．考试时间：%s。" % time_min,
           "2．请首先按要求在试卷的标封处填写您的姓名、准考证号和所在单位的名称。",
           "3．请仔细阅读各种题目的回答要求，在规定的位置填写您的答案。",
           "4．不要在试卷上乱写乱画，不要在标封区填写无关的内容。", "",
           "> 满分 %s 分，共 %d 题；题号全卷连续编号。" % (_num(score_all), n_all), ""]
    cn = "一二三四五六七八九"
    no = 0
    for i, sec in enumerate(sections):
        qs = {q["n"]: q for q in b["sections"][sec["type"]]}
        total = sec.get("total") or sec["each"] * len(sec["ids"])
        start, no = no + 1, no + len(sec["ids"])
        out.append("%s、%s（第%d～%d题）%s每题 %s 分，共 %s 分" % (
            cn[i], sec["type"], start, no, sec.get("desc", ""), sec["each"], _num(total)))
        out.append("")
        for k, n in enumerate(sec["ids"]):
            q = qs[n]
            num = start + k
            if sec["type"] == "判断题":
                out.append("(    ) %d. %s" % (num, q["stem"]))
            else:
                out.append("%d. %s" % (num, q["stem"]))
                for letter in sorted(q["opts"]):
                    out.append("（%s）%s" % (letter, q["opts"][letter]))
            if with_answers:
                out.append("    【答案】%s" % (q["ans"] or "（原卷未给答案）"))
            out.append("")
    return "\n".join(out)


def _num(x):
    return ("%g" % x) if isinstance(x, float) else str(x)


def render_ops(level, slots, with_key=False):
    pool = {o["name"]: o for o in lib.load_ops(level)}
    out = ["# 人工智能训练师（%s级）操作技能考核" % ("三" if level == "3" else "四"), "",
           "## 注　意　事　项", "",
           "1.考生根据操作技能考核通知单中所列的试题做好考核准备；",
           "2.请考生仔细阅读试题单中具体考核内容和要求，并按要求完成操作或进行笔答或口答，"
           "若有笔答请考生在答题卷上完成。",
           "3.操作技能考核时要遵守考场纪律，服从考场管理人员指挥，以保证考核安全顺利进行。", "",
           "## 考核通知单", "",
           "| 试题 | 试题代码 | 试题名称 | 考核时间 | 配分 |", "|---|---|---|---|---|"]
    for i, s in enumerate(slots, 1):
        out.append("| 试题%d | %s | %s | %s | %d分 |" % (i, s.get("code") or "-", s["name"],
                                                        s.get("time") or "-", s["score"]))
    out.append("| 合计 | | | %s | %d分 |" % (_sumtime(slots), sum(s["score"] for s in slots)))
    for i, s in enumerate(slots, 1):
        it = pool.get(s["name"], {})
        out += ["", "---", "", "## 试题%d" % i, "",
                "试题代码：%s" % (s.get("code") or "-"),
                "试题名称：%s" % s["name"],
                "考核时间：%s　　配分：%d分" % (s.get("time") or "-", s["score"]), ""]
        for label, key in (("场地设备要求", "site"), ("工作任务", "task"),
                           ("技能要求", "skill"), ("质量指标", "quality")):
            if it.get(key):
                out += ["### %s" % label, it[key], ""]
        if with_key:
            if it.get("rubric"):
                out += ["### 评分表", ""]
                for r in it["rubric"]:
                    out.append("- %s（%d分）%s" % (r["id"], r["score"], r["desc"]))
                out.append("")
            if it.get("answers"):
                out += ["### 参考答案", "", "```text", it["answers"], "```", ""]
            else:
                out += ["> 本题原卷未附参考答案，请对照评分表自评或让 AI 给出参考方案。", ""]
    return "\n".join(out)


def _sumtime(slots):
    mins = 0
    for s in slots:
        t = (s.get("time") or "").replace("min", "")
        mins += int(t) if t.isdigit() else 0
    return "%dmin" % mins


# ---------------------------------------------------------------- 组卷
def gen_theory(level, seed=None, mode="mixed"):
    c = comp(level, "theory")
    rng = random.Random(seed)
    b = lib.load_bank(level)
    sections, warn = [], []
    for sec in c["sections"]:
        pool = b["sections"][sec["type"]]
        k = min(sec["count"], len(pool))
        if k < sec["count"]:
            warn.append("%s 题量不足（需%d，实际%d）" % (sec["type"], sec["count"], k))
        if mode == "graded":
            # 只用有官方答案的题，保证整卷可机判（题量不足会告警）
            cand = [q["n"] for q in pool if q["ans"]]
        else:
            cand = [q["n"] for q in pool]
        ids = rng.sample(cand, min(k, len(cand)))
        sections.append({"type": sec["type"], "each": sec["each"],
                         "total": sec["total"], "desc": sec.get("desc", ""), "ids": ids})
    return {"kind": "theory", "level": str(level), "name": c["name"], "time": c["time"],
            "sections": sections, "warn": warn}


def gen_ops(level, seed=None):
    c = comp(level, "ops")
    rng = random.Random(seed)
    pool = lib.load_ops(level)
    slots, used = [], set()
    for slot in c["slots"]:
        cand = [o for o in pool if o["name"] not in used]
        code = slot.get("code") or ""
        # 先按二级模块（如 2.2）匹配，退一级（2），再退到整库随机
        tiers = [[o for o in cand if code[:3] and (o.get("code") or "").startswith(code[:3])],
                 [o for o in cand if code[:1] and (o.get("code") or "").startswith(code[:1])],
                 cand]
        pick = rng.choice(next((t for t in tiers if t), []) or [None]) if cand else None
        if pick is None:
            continue
        used.add(pick["name"])
        slots.append({"code": pick.get("code") or slot.get("code"), "name": pick["name"],
                      "score": slot["score"], "time": slot.get("time") or pick.get("time")})
    return {"kind": "ops", "level": str(level), "name": c["name"],
            "time": _sumtime(slots), "slots": slots, "warn": []}


# ---------------------------------------------------------------- 命令
def new_id(level, kind):
    s = "".join(random.choice("0123456789abcdef") for _ in range(4))
    return "%s-%s%s-%s" % (time.strftime("%Y%m%d"), level, "T" if kind == "theory" else "O", s)


def save_paper(p):
    os.makedirs(PAPERS, exist_ok=True)
    path = os.path.join(PAPERS, p["id"] + ".json")
    lib.save_json(path, p)
    md = render_theory(p["level"], p["sections"], p["time"]) if p["kind"] == "theory" \
        else render_ops(p["level"], p["slots"])
    with open(os.path.join(PAPERS, p["id"] + ".md"), "w", encoding="utf-8") as f:
        f.write(md)
    return path


def load_paper(pid):
    path = os.path.join(PAPERS, pid + ".json")
    if os.path.exists(path):
        return lib.load_json(path, {})
    # 官方卷不落盘，按 manifest 现场还原
    m = lib.manifest()
    p = next((x for x in m["papers"] if x["id"] == pid), None)
    if not p:
        raise SystemExit("找不到试卷 %s，先 mock.py papers 看看" % pid)
    if p["kind"] == "theory":
        c = comp(p["level"], "theory")
        each = {x["type"]: x for x in c["sections"]}
        p = dict(p, time=c["time"], sections=[
            {"type": x["type"], "each": each[x["type"]]["each"], "ids": x["ids"],
             "total": each[x["type"]]["total"], "desc": each[x["type"]].get("desc", "")}
            for x in p["sections"]])
    return p


def cmd_official(a):
    m = lib.manifest()
    pid = "official-%s-%s" % (a.level, a.kind)
    p = next((x for x in m["papers"] if x["id"] == pid), None)
    if not p:
        raise SystemExit("manifest 里没有官方卷 %s" % pid)
    if a.kind == "theory":
        c = comp(a.level, "theory")
        each = {s["type"]: s["each"] for s in c["sections"]}
        secs = [{"type": s["type"], "each": each[s["type"]], "ids": s["ids"],
                 "desc": next(x.get("desc", "") for x in c["sections"] if x["type"] == s["type"])}
                for s in p["sections"]]
        print(render_theory(a.level, secs, c["time"], with_answers=a.key))
    else:
        print(render_ops(a.level, p["slots"], with_key=a.key))


def cmd_gen(a):
    p = gen_theory(a.level, a.seed, a.mode) if a.kind == "theory" else gen_ops(a.level, a.seed)
    p["id"] = new_id(a.level, p["kind"])
    p["created"] = time.strftime("%Y-%m-%d %H:%M")
    p["source"] = "随机组卷"
    path = save_paper(p)
    for w in p.get("warn", []):
        print("⚠ %s" % w)
    print("试卷编号：%s（已存 %s）" % (p["id"], path))
    if p["kind"] == "theory":
        b = lib.load_bank(p["level"])
        tot = ok = 0
        for sec in p["sections"]:
            qs = {q["n"]: q for q in b["sections"][sec["type"]]}
            tot += len(sec["ids"])
            ok += sum(1 for n in sec["ids"] if qs[n]["ans"])
        print("本卷 %d 题中 %d 题有官方答案（可机判），%d 题原卷无答案（需 AI 判定）。"
              % (tot, ok, tot - ok))
    print()
    print(render_theory(p["level"], p["sections"], p["time"]) if p["kind"] == "theory"
          else render_ops(p["level"], p["slots"]))


def cmd_key(a):
    p = load_paper(a.paper)
    if p["kind"] == "theory":
        print(render_theory(p["level"], p["sections"], p["time"], with_answers=True))
    else:
        print(render_ops(p["level"], p["slots"], with_key=True))


def cmd_grade(a):
    p = load_paper(a.paper)
    if p["kind"] != "theory":
        raise SystemExit("操作技能卷不能自动判分，用 key 命令查看评分表自评")
    b = lib.apply_corrections(lib.load_bank(p["level"]))
    user = answer_pairs(a.answers)
    idx = {}
    j = 0
    for sec in p["sections"]:
        qs = {q["n"]: q for q in b["sections"][sec["type"]]}
        for n in sec["ids"]:
            j += 1
            idx[j] = (sec, qs[n])
    score = 0.0
    full = 0.0
    wrong, unknown, no_ans = [], [], []
    gradable = correct_n = answered_n = 0
    for j, (sec, q) in sorted(idx.items()):
        each = sec["each"]
        if not q["ans"]:
            no_ans.append(j)
            continue
        full += each
        gradable += 1
        if j not in user:
            continue
        answered_n += 1
        ok, off = lib.grade_one(q, user[j])
        if ok is None:
            unknown.append((j, user[j], q))
        elif ok:
            score += each
            correct_n += 1
        else:
            wrong.append((j, user[j], off, q, sec["type"]))
    print("### %s　%s" % (p["name"], p["id"]))
    print("未作答：%d 题" % (len(idx) - len(user)))
    print("机判成绩：%.1f / %.1f（官方答案覆盖 %d/%d 题，正确率 %.0f%%）"
          % (score, full, gradable, len(idx), 100.0 * score / max(0.01, full)))
    if no_ans:
        print("原卷未给答案、需 AI 判定：%d 题（第%s题）"
              % (len(no_ans), "、".join(str(x) for x in no_ans[:30]) + ("…" if len(no_ans) > 30 else "")))
    if unknown:
        print("你的作答落在无答案题上，需 AI 判定：%s" % "、".join(str(j) for j, _, _ in unknown))
    if wrong:
        print("\n**错题**")
        for j, u, off, q, tp in wrong:
            print("- 第%d题（%s）你答 %s，正确 %s：%s" % (j, tp, u, off, q["stem"]))
            for k in sorted(q["opts"]):
                print("    （%s）%s" % (k, q["opts"][k]))
    wb = lib.load_json(os.path.join(lib.RECORDS, "wrongbook.json"), {})
    for j, u, off, q, tp in wrong:
        wb["%s:%s:%d" % (p["level"], tp, q["n"])] = {
            "level": p["level"], "type": tp, "n": q["n"], "stem": q["stem"][:60],
            "my": u, "correct": off, "ts": time.strftime("%Y-%m-%d %H:%M")}
    lib.save_json(os.path.join(lib.RECORDS, "wrongbook.json"), wb)
    hist = lib.load_json(os.path.join(lib.RECORDS, "history.json"), [])
    hist.append({"ts": time.strftime("%Y-%m-%d %H:%M"), "level": p["level"], "type": "模拟卷",
                 "right": correct_n, "total": answered_n, "score": round(score, 1),
                 "full": round(full, 1), "unknown": len(unknown), "paper": p["id"]})
    lib.save_json(os.path.join(lib.RECORDS, "history.json"), hist[-500:])


def cmd_papers(a):
    if not os.path.isdir(PAPERS):
        print("还没有生成过试卷")
        return
    files = sorted(f for f in os.listdir(PAPERS) if f.endswith(".json"))
    if not files:
        print("还没有生成过试卷")
        return
    for f in files:
        p = lib.load_json(os.path.join(PAPERS, f), {})
        n = sum(len(s["ids"]) for s in p.get("sections", [])) or len(p.get("slots", []))
        print("- %s  %s级 %s %s 题量%d" % (p.get("id"), p.get("level"),
                                          "理论" if p.get("kind") == "theory" else "操作技能",
                                          p.get("created", ""), n))


def main():
    ap = argparse.ArgumentParser(description="模拟试卷生成与判分")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("official")
    s.add_argument("--level", required=True, choices=["3", "4"])
    s.add_argument("--kind", default="theory", choices=["theory", "ops"])
    s.add_argument("--key", action="store_true")
    s.set_defaults(fn=cmd_official)

    s = sub.add_parser("gen")
    s.add_argument("--level", required=True, choices=["3", "4"])
    s.add_argument("--kind", default="theory", choices=["theory", "ops"])
    s.add_argument("--seed", type=int)
    s.add_argument("--mode", default="mixed", choices=["mixed", "graded"],
                   help="mixed=全库随机（部分题需AI判定）；graded=只取有官方答案的题")
    s.set_defaults(fn=cmd_gen)

    s = sub.add_parser("key")
    s.add_argument("--paper", required=True)
    s.set_defaults(fn=cmd_key)

    s = sub.add_parser("grade")
    s.add_argument("--paper", required=True)
    s.add_argument("--answers", required=True)
    s.set_defaults(fn=cmd_grade)

    sub.add_parser("papers").set_defaults(fn=cmd_papers)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
