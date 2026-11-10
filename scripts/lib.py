#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享库：读写题库 md、渲染试卷、统计。无第三方依赖。"""
import json
import os
import re
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RECORDS = os.path.join(ROOT, "records")
TYPES = ("判断题", "单选题", "多选题")
OPT_LETTERS = "ABCDE"


# ---------------------------------------------------------------- md 读写
def _esc(s):
    return (s or "").replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _unesc(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(s[i + 1])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _split(line):
    """按未转义的 | 切分"""
    parts, buf, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            buf.append(line[i:i + 2])
            i += 2
            continue
        if c == "|":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def load_bank(level):
    """返回 {'level','title','sections':{type:[q]}}；q={'n','ans','stem','opts'}"""
    path = os.path.join(DATA, "bank-%s.md" % level)
    if not os.path.exists(path):
        raise SystemExit("找不到题库文件：%s" % path)
    bank = {"level": str(level), "title": "", "sections": {t: [] for t in TYPES}}
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("# ") and not bank["title"]:
                bank["title"] = line[2:].strip()
                continue
            if line.startswith("## "):
                name = line[3:].strip()
                cur = name if name in TYPES else None
                continue
            if line.startswith("#") or line.startswith(">"):
                continue
            if cur is None:
                continue
            f_ = _split(line)
            if len(f_) < 3:
                continue
            q = {"n": int(f_[0]), "ans": _unesc(f_[1]).strip(),
                 "stem": _unesc(f_[2]), "opts": {}}
            for seg in f_[3:]:
                seg = _unesc(seg)
                m = re.match(r"^([A-E])[:：]\s*(.*)$", seg)
                if m:
                    q["opts"][m.group(1)] = m.group(2).strip()
            bank["sections"][cur].append(q)
    return bank


def save_bank(bank):
    path = os.path.join(DATA, "bank-%s.md" % bank["level"])
    lines = ["# %s" % bank["title"], "> 格式：题号|答案|题干|A:选项|B:选项…（答案为空表示原卷未给答案）"]
    for t in TYPES:
        qs = bank["sections"].get(t) or []
        if not qs:
            continue
        lines.append("## %s" % t)
        for q in qs:
            row = ["%d" % q["n"], _esc(q["ans"]), _esc(q["stem"])]
            for k in sorted(q["opts"]):
                row.append("%s:%s" % (k, _esc(q["opts"][k])))
            lines.append("|".join(row))
    os.makedirs(DATA, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- 操作技能
def load_ops(level):
    path = os.path.join(DATA, "ops-%s.md" % level)
    if not os.path.exists(path):
        raise SystemExit("找不到操作技能题库：%s" % path)
    items, cur, field, buf = [], None, None, []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("## "):
                if cur:
                    if field:
                        cur[field] = "\n".join(buf).strip()
                    items.append(cur)
                head = line[3:].strip()
                m = re.match(r"^([\d.]+)\s+(.*)$", head)
                if m:
                    code, name = m.group(1), m.group(2)
                else:
                    code, name = "", re.sub(r"^[-—]\s*", "", head)
                cur = {"code": code, "name": name,
                       "time": "", "score": "", "site": "", "task": "", "skill": "",
                       "quality": "", "rubric": [], "answers": ""}
                field, buf = None, []
                continue
            if cur is None:
                continue
            if line.startswith("### "):
                if field:
                    cur[field] = "\n".join(buf).strip()
                name = line[4:].strip()
                field = {"场地设备要求": "site", "工作任务": "task", "技能要求": "skill",
                         "质量指标": "quality", "参考答案": "answers"}.get(name)
                buf = []
                continue
            m = re.match(r"^M(\d+)\|(\d+)\|(.*)$", line)
            if m and line.startswith("M"):
                cur["rubric"].append({"id": "M" + m.group(1), "score": int(m.group(2)),
                                      "desc": m.group(3)})
                continue
            if field is None:
                m = re.match(r"^-\s*(考核时间|配分)[:：]\s*(.*)$", line)
                if m:
                    v = m.group(2).strip()
                    cur["time" if m.group(1) == "考核时间" else "score"] = v
                continue
            buf.append(line)
    if cur:
        if field:
            cur[field] = "\n".join(buf).strip()
        items.append(cur)
    for it in items:
        it["score"] = re.sub(r"[^\d]", "", it.get("score", "") or "")
    return items


# ---------------------------------------------------------------- 渲染
def fmt_question(q, idx=None, show_ans=False, type_name=None, show_no=True):
    n = idx if idx is not None else q.get("n")
    no = ("%s. " % n) if show_no else ""
    if type_name == "判断题":
        head = "（    ）%s%s" % (no, q["stem"])
        body = []
        if show_ans and q["ans"]:
            body.append("    √ 答案：%s" % q["ans"])
    else:
        head = "%s%s" % (no, q["stem"])
        body = []
        for k in sorted(q["opts"]):
            body.append("    （%s）%s" % (k, q["opts"][k]))
        if show_ans:
            body.append("    答案：%s" % (q["ans"] or "（原卷未给答案）"))
    return "\n".join([head] + body)


def grade_one(q, user):
    """返回 (correct, official) ; official 为 None 表示无官方答案"""
    off = (q["ans"] or "").strip().upper().replace("√", "√").replace("V", "√")
    if not off:
        return None, None
    u = (user or "").strip().upper()
    u = u.replace("对", "√").replace("错", "×").replace("T", "√").replace("F", "×").replace("V", "√")
    if off[0] in "√×":
        return (u == off), off
    n_user = "".join(sorted(set(ch for ch in u if ch in OPT_LETTERS)))
    return (n_user == "".join(sorted(set(off)))), off


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def manifest():
    return load_json(os.path.join(DATA, "manifest.json"), {})


def corrections():
    return load_json(os.path.join(RECORDS, "corrections.json"), {})


def apply_corrections(bank):
    """用户/AI 修订覆盖：key = 'level:type:num'"""
    cor = corrections()
    if not cor:
        return bank
    for t, qs in bank["sections"].items():
        for q in qs:
            k = "%s:%s:%d" % (bank["level"], t, q["n"])
            if k in cor:
                q["ans"] = cor[k]["ans"]
                q["ans_src"] = cor[k].get("src", "user")
    return bank


def pick_note(qs, n, rng):
    return rng.sample(qs, min(n, len(qs)))
