#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全题库练习：抽题、看答案、判分、错题本、统计。

用法示例：
  python3 practice.py list
  python3 practice.py show --level 3 --type 判断题 --from 1 --to 10
  python3 practice.py show --level 3 --type 单选题 --from 1 --to 5 --ans
  python3 practice.py random --level 3 -n 10 --type 多选题 --seed 7
  python3 practice.py search --level 4 -q 数据清洗
  python3 practice.py grade --level 3 --type 判断题 --answers "1:√,2:×,3:√"
  python3 practice.py annotate --level 3 --type 判断题 --n 5 --ans √ --src ai
  python3 practice.py wrong
  python3 practice.py stats
"""
import argparse
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

WRONG = os.path.join(lib.RECORDS, "wrongbook.json")
HIST = os.path.join(lib.RECORDS, "history.json")
CORR = os.path.join(lib.RECORDS, "corrections.json")


def answer_pairs(text):
    """'1:√,2:×,3:ABC' → {1:'√',2:'×',3:'ABC'}"""
    out = {}
    for m in re.finditer(r"(\d{1,3})\s*[:：、．.,]?\s*([√×✓✗A-Ea-e]{1,5})", text or ""):
        v = m.group(2).upper().replace("✓", "√").replace("✗", "×")
        out[int(m.group(1))] = v
    return out


def cmd_list(a):
    m = lib.manifest()
    for lv in ("3", "4"):
        b = lib.apply_corrections(lib.load_bank(lv))
        ops = lib.load_ops(lv)
        cnt = "，".join("%s %d题（有官方答案%d）" % (t, len(qs), sum(1 for q in qs if q["ans"]))
                       for t, qs in b["sections"].items() if qs)
        print("【%s级】理论：%s" % ("三" if lv == "3" else "四", cnt))
        print("        操作技能：%d 道试题（含评分表 %d，含参考答案 %d）"
              % (len(ops), sum(1 for o in ops if o["rubric"]), sum(1 for o in ops if o["answers"])))
    print("提示：理论题库答案来自官方模拟卷覆盖到的题目；未覆盖题目标注为“原卷未给答案”。")


def cmd_show(a):
    b = lib.apply_corrections(lib.load_bank(a.level))
    qs = b["sections"].get(a.type) or []
    if not qs:
        raise SystemExit("%s级没有%s" % (a.level, a.type))
    lo = a.start or 1
    hi = a.end or len(qs)
    sel = [q for q in qs if lo <= q["n"] <= hi]
    print("### %s %s 第%d-%d题（共%d题）" % (b["title"], a.type, lo, hi, len(sel)))
    for q in sel:
        print(lib.fmt_question(q, show_ans=a.ans, type_name=a.type))
        print()


def cmd_random(a):
    rng = random.Random(a.seed)
    b = lib.apply_corrections(lib.load_bank(a.level))
    types = [a.type] if a.type else [t for t in lib.TYPES if b["sections"].get(t)]
    if a.type and not b["sections"].get(a.type):
        raise SystemExit("%s级题库没有%s" % (a.level, a.type))
    picked = []
    per = max(1, a.n // len(types))
    for i, t in enumerate(types):
        n = per if i < len(types) - 1 else a.n - per * (len(types) - 1)
        picked += [(t, q) for q in rng.sample(b["sections"][t], min(n, len(b["sections"][t])))]
    print("### 随机抽题 %d 道（%s级，seed=%s）" % (len(picked), a.level, a.seed))
    for i, (t, q) in enumerate(picked, 1):
        print("%d）[%s 原题#%d] %s" % (i, t, q["n"],
                                       lib.fmt_question(q, show_ans=a.ans, type_name=t, show_no=False)))
        print()


def cmd_search(a):
    b = lib.apply_corrections(lib.load_bank(a.level))
    kw = a.q
    hit = 0
    for t, qs in b["sections"].items():
        for q in qs:
            blob = q["stem"] + "".join(q["opts"].values())
            if kw in blob:
                hit += 1
                print("[%s #%d] %s" % (t, q["n"], lib.fmt_question(q, show_ans=a.ans, type_name=t)))
                print()
                if hit >= a.limit:
                    print("（已显示 %d 条，可用 --limit 调整）" % a.limit)
                    return
    print("命中 %d 条" % hit)


def cmd_grade(a):
    b = lib.apply_corrections(lib.load_bank(a.level))
    qs = {q["n"]: q for q in (b["sections"].get(a.type) or [])}
    user = answer_pairs(a.answers)
    if not user:
        raise SystemExit("没解析到答案，格式示例：--answers \"1:√,2:×,3:A,4:ABC\"")
    right, wrong, unknown = [], [], []
    for n, u in sorted(user.items()):
        q = qs.get(n)
        if not q:
            continue
        ok, off = lib.grade_one(q, u)
        if ok is None:
            unknown.append((n, u, q))
        elif ok:
            right.append((n, u, off))
        else:
            wrong.append((n, u, off, q))
    total = len(right) + len(wrong)
    print("### 判分结果（%s级 %s）" % (a.level, a.type))
    if total:
        print("得分：%d/%d（%.1f%%）" % (len(right), total, 100.0 * len(right) / total))
    if wrong:
        print("\n**错题**")
        for n, u, off, q in wrong:
            print("- 第%d题 你的答案：%s ／ 正确：%s" % (n, u, off))
            print("  %s" % q["stem"])
            for k in sorted(q["opts"]):
                print("    （%s）%s" % (k, q["opts"][k]))
    if unknown:
        print("\n**以下题目原卷未给答案，需 AI 判定**：%s" % "、".join("第%d题(你答%s)" % (n, u) for n, u, _ in unknown))
        for n, u, q in unknown:
            print("- 第%d题：%s" % (n, q["stem"]))
    # 记录
    wb = lib.load_json(WRONG, {})
    for n, u, off, q in wrong:
        key = "%s:%s:%d" % (a.level, a.type, n)
        wb[key] = {"level": a.level, "type": a.type, "n": n, "stem": q["stem"][:60],
                   "my": u, "correct": off, "ts": time.strftime("%Y-%m-%d %H:%M")}
    lib.save_json(WRONG, wb)
    hist = lib.load_json(HIST, [])
    hist.append({"ts": time.strftime("%Y-%m-%d %H:%M"), "level": a.level, "type": a.type,
                 "right": len(right), "total": total, "unknown": len(unknown)})
    lib.save_json(HIST, hist[-500:])


def cmd_annotate(a):
    cor = lib.load_json(CORR, {})
    key = "%s:%s:%d" % (a.level, a.type, a.n)
    cor[key] = {"ans": a.ans.strip().upper(), "src": a.src, "ts": time.strftime("%Y-%m-%d %H:%M")}
    lib.save_json(CORR, cor)
    print("已记录：%s = %s（来源：%s）" % (key, a.ans, a.src))


def cmd_wrong(a):
    wb = lib.load_json(WRONG, {})
    if a.rm:
        for k in a.rm:
            wb.pop(k.strip(), None)
        lib.save_json(WRONG, wb)
        print("已从错题本移除：%s（剩余 %d 条）" % ("、".join(a.rm), len(wb)))
        return
    if a.clear:
        lib.save_json(WRONG, {})
        print("错题本已清空")
        return
    if not wb:
        print("错题本为空")
        return
    print("### 错题本（%d 条）" % len(wb))
    for k, v in sorted(wb.items()):
        print("- [%s级 %s #%d] %s ／ 你答 %s，正确 %s（%s）"
              % (v["level"], v["type"], v["n"], v["stem"], v["my"], v["correct"], v["ts"]))


def cmd_stats(a):
    hist = lib.load_json(HIST, [])
    if not hist:
        print("还没有练习记录")
        return
    tot_r = sum(h["right"] for h in hist)
    tot_q = sum(h["total"] for h in hist)
    print("### 练习统计（共 %d 次）" % len(hist))
    print("累计：%d/%d，正确率 %.1f%%" % (tot_r, tot_q, 100.0 * tot_r / max(1, tot_q)))
    by = {}
    for h in hist:
        d = by.setdefault((h["level"], h["type"]), [0, 0])
        d[0] += h["right"]
        d[1] += h["total"]
    for (lv, t), (r, q) in sorted(by.items()):
        print("  %s级 %s：%d/%d（%.0f%%）" % (lv, t, r, q, 100.0 * r / max(1, q)))
    print("错题本：%d 条" % len(lib.load_json(WRONG, {})))


def main():
    ap = argparse.ArgumentParser(description="人工智能训练师理论题库练习")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(fn=cmd_list)

    s = sub.add_parser("show")
    s.add_argument("--level", required=True, choices=["3", "4"])
    s.add_argument("--type", required=True, choices=list(lib.TYPES))
    s.add_argument("--from", dest="start", type=int)
    s.add_argument("--to", dest="end", type=int)
    s.add_argument("--ans", action="store_true")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("random")
    s.add_argument("--level", required=True, choices=["3", "4"])
    s.add_argument("--type", choices=list(lib.TYPES))
    s.add_argument("-n", type=int, default=10)
    s.add_argument("--seed", type=int)
    s.add_argument("--ans", action="store_true")
    s.set_defaults(fn=cmd_random)

    s = sub.add_parser("search")
    s.add_argument("--level", required=True, choices=["3", "4"])
    s.add_argument("-q", required=True)
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--ans", action="store_true")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("grade")
    s.add_argument("--level", required=True, choices=["3", "4"])
    s.add_argument("--type", required=True, choices=list(lib.TYPES))
    s.add_argument("--answers", required=True)
    s.set_defaults(fn=cmd_grade)

    s = sub.add_parser("annotate")
    s.add_argument("--level", required=True, choices=["3", "4"])
    s.add_argument("--type", required=True, choices=list(lib.TYPES))
    s.add_argument("--n", type=int, required=True)
    s.add_argument("--ans", required=True)
    s.add_argument("--src", default="ai")
    s.set_defaults(fn=cmd_annotate)

    s = sub.add_parser("wrong")
    s.add_argument("--clear", action="store_true")
    s.add_argument("--rm", nargs="+", metavar="级别:题型:题号")
    s.set_defaults(fn=cmd_wrong)

    sub.add_parser("stats").set_defaults(fn=cmd_stats)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
