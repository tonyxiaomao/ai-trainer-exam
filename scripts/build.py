#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把原始 Word 题库/模拟卷转成紧凑 md（数据管线）。

用法：
  python3 build.py rebuild [--src3 DIR] [--src4 DIR]     # 从 8 份原始文档全量重建
  python3 build.py theory <docx> --level 3 --append      # 追加一份理论题库文档
  python3 build.py ops <doc|docx> --level 3 --append     # 追加一份操作技能文档
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

try:
    import docx
except ImportError:
    raise SystemExit("需要 python-docx：pip install python-docx")

HEAD_RE = re.compile(r"^(?:[一二三四五六七八九十]+、\s*)?(判断题|单选题|多选题)\s*[（(]")
JUDGE_RE = re.compile(r"^[（(]\s*[）)]\s*(\d+)\s*[.、．]\s*(.*)$")
NUM_RE = re.compile(r"^(\d+)\s*[.、．]\s*(.*)$")
OPT_RE = re.compile(r"^[（(]\s*([A-Ea-e])\s*[）)]\s*(.*)$")
OPS_HEAD_RE = re.compile(r"^(试题代码|试题名称|考核时间|配分)[:：]\s*(.*)$")
OPS_SEC_RE = re.compile(r"^[1-4]\s*[.、．]\s*(场地设备要求|工作任务|技能要求|质量指标)\s*$")


# ---------------------------------------------------------------- 输入
def txt_lines(path):
    """.doc 走 textutil -> txt，保留表格单元格之间的空格（docx 转换会丢）"""
    if not shutil.which("textutil"):
        raise SystemExit("解析 .doc 需要 macOS textutil，或先手动另存为 .docx")
    out = os.path.join(tempfile.mkdtemp(), "out.txt")
    subprocess.run(["textutil", "-convert", "txt", "-encoding", "UTF-8",
                    "-output", out, path], check=True)
    with open(out, encoding="utf-8") as f:
        # textutil 用 \x07 作为表格单元格分隔符
        return [re.sub(r"[\x00-\x08\x0b\x0c]", " ", ln).replace("\u3000", " ").strip()
                for ln in f if ln.strip()]


def to_docx(path):
    """doc/docx → docx 路径（doc 用 macOS textutil 转换）"""
    if path.lower().endswith(".docx"):
        return path
    if not shutil.which("textutil"):
        raise SystemExit("转换 .doc 需要 macOS textutil，或先手动另存为 .docx")
    out = os.path.join(tempfile.mkdtemp(), os.path.splitext(os.path.basename(path))[0] + ".docx")
    subprocess.run(["textutil", "-convert", "docx", "-output", out, path], check=True)
    return out


def paragraphs(path):
    if path.lower().endswith(".doc"):
        return txt_lines(path)
    d = docx.Document(path)
    return [p.text.replace("\u3000", " ").strip() for p in d.paragraphs if p.text.strip()]


# ---------------------------------------------------------------- 理论题
def parse_theory(paras):
    sec = {t: [] for t in lib.TYPES}
    cur, buf = None, None

    def flush():
        if buf and cur:
            sec[cur].append(buf)

    for ln in paras:
        m = HEAD_RE.match(ln)
        if m:
            flush()
            cur, buf = m.group(1), None
            continue
        if cur is None:
            continue
        if cur == "判断题":
            jm = JUDGE_RE.match(ln)
            if jm:
                flush()
                buf = {"n": int(jm.group(1)), "stem": jm.group(2).strip(), "opts": {}, "ans": ""}
            elif buf:
                buf["stem"] += ln
            continue
        nm = NUM_RE.match(ln)
        if nm:
            flush()
            buf = {"n": int(nm.group(1)), "stem": nm.group(2).strip(), "opts": {}, "ans": ""}
            continue
        om = OPT_RE.match(ln)
        if om and buf:
            buf["opts"][om.group(1).upper()] = om.group(2).strip()
            continue
        if not buf:
            continue
        need = 4 if cur == "单选题" else 5
        if len(buf["opts"]) < need and len(ln) <= 120 and not ln.endswith("。"):
            nxt = lib.OPT_LETTERS[len(buf["opts"])]      # 原卷偶有漏标 (D)
            buf["opts"][nxt] = ln
        elif buf["opts"]:
            k = max(buf["opts"])
            buf["opts"][k] += ln
        else:
            buf["stem"] += ln
    flush()
    return sec


def parse_answers(paras):
    ans = {t: {} for t in lib.TYPES}
    mode, rng = None, 1
    for ln in paras:
        if "判断题参考答案" in ln:
            mode = "判断题"
        elif "单选题参考答案" in ln:
            mode = "单选题"
        elif "多选题参考答案" in ln:
            mode = "多选题"
        if mode == "判断题":
            r = re.search(r"(\d+)\s*-\s*\d+\s*[）)]", ln)
            if r:
                rng = int(r.group(1))
            syms = re.findall(r"[√×✓✗]", ln)
            for i, s in enumerate(syms):
                ans["判断题"][rng + i] = "√" if s in "√✓" else "×"
        elif mode == "单选题":
            for r in re.finditer(r"(\d+)\s*-\s*\d+\s*[）)]\s*([A-E]{5,})", ln):
                for i, ch in enumerate(r.group(2)):
                    ans["单选题"][int(r.group(1)) + i] = ch
        elif mode == "多选题":
            for r in re.finditer(r"(?:^|\s)(\d+)\s*[）)]\s*([A-E]{1,5})(?=\s|$)", ln):
                ans["多选题"][int(r.group(1))] = r.group(2)
    return ans


def norm(s):
    return re.sub(r"[\s（）()\[\]【】，,。.．、；;：:“”\"'？?！!\-—_/|]+", "", s or "")


# ---------------------------------------------------------------- 操作技能
def parse_ops(paras):
    items, cur, field, buf = [], None, None, []

    def close_field():
        if cur is not None and field:
            txt = "\n".join(buf).strip()
            if txt:
                old = cur.get(field, "")
                cur[field] = (old + "\n" + txt).strip() if old else txt

    def close_item():
        close_field()
        if cur and cur["name"]:
            items.append(cur)

    for ln in paras:
        m = OPS_HEAD_RE.match(ln)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key == "试题代码":
                close_item()
                cur = {"code": val, "name": "", "time": "", "score": "", "site": "", "task": "",
                       "skill": "", "quality": "", "rubric": [], "answers": ""}
                field, buf = None, []
            elif cur is not None:
                cur[{"试题名称": "name", "考核时间": "time", "配分": "score"}[key]] = val
            continue
        if cur is None:
            continue
        if "评分表" in ln and len(ln) < 20 or ln.startswith("细则编号"):
            close_field()
            field, buf = "rubric_text", []
            continue
        if ln.startswith("参考答案"):
            close_field()
            field, buf = "answers", []
            continue
        s = OPS_SEC_RE.match(ln)
        if s:
            close_field()
            field = {"场地设备要求": "site", "工作任务": "task",
                     "技能要求": "skill", "质量指标": "quality"}[s.group(1)]
            buf = []
            continue
        if ln.startswith("人工智能训练师（") or ln in ("试题单", "试题评分表及答案", "试题评分表") \
                or ln.startswith("准考证号") or ln.startswith("姓名：") or ln.startswith("考核日期"):
            continue
        if re.match(r"^试题\d+$", ln) or ln.startswith("第") and "部分" in ln:
            continue
        if field:
            buf.append(ln)
    close_item()

    out = []
    for it in items:
        if not it.get("code"):
            blob = "\n".join(filter(None, [it.get("task"), it.get("answers"), it.get("site")]))
            m = re.search(r"(?<!\d)([1-4]\.\d\.\d)(?!\d)", blob)
            if m:
                it["code"] = m.group(1)      # 原卷漏填试题代码时，从任务书里引用的 ipynb/文件名补
        rub = []
        if it.get("rubric_text"):
            txt = it["rubric_text"]
            total = re.search(r"合计配分\s*(\d+)", txt)
            body = txt[:total.start()] if total else txt
            for m in re.finditer(r"(M\d+)\s+(\d+)\s+(.*?)(?=M\d+\s+\d+\s|$)", body):
                desc = m.group(3).strip()
                desc = re.sub(r"(根据数据|根据代码|根据答案|根据)\s*$", "", desc).strip()
                rub.append({"id": m.group(1), "score": int(m.group(2)), "desc": desc})
            it["score"] = it["score"] or (total.group(1) + "分" if total else "")
            del it["rubric_text"]
        it["rubric"] = rub
        it["score"] = re.sub(r"[^\d]", "", it.get("score", "") or "")
        out.append(it)
    return out


def merge_ops(pool, new):
    idx = {(it["code"], it["name"]): it for it in pool}
    by_name = {it["name"]: it for it in pool}
    for it in new:
        key = (it["code"], it["name"])
        tgt = idx.get(key) or by_name.get(it["name"])
        if tgt:
            for f in ("site", "task", "skill", "quality", "answers", "score", "time", "code"):
                if not tgt.get(f) and it.get(f):
                    tgt[f] = it[f]
            if it.get("rubric") and not tgt.get("rubric"):
                tgt["rubric"] = it["rubric"]
        else:
            pool.append(it)
            idx[key] = it
            by_name[it["name"]] = it
    return pool


def dedupe_ops(pool):
    seen, out = {}, []
    for it in pool:
        key = it["name"]
        if key in seen:
            tgt = seen[key]
            for f in ("site", "task", "skill", "quality", "answers", "score", "time", "code"):
                if not tgt.get(f) and it.get(f):
                    tgt[f] = it[f]
            if it.get("rubric") and not tgt.get("rubric"):
                tgt["rubric"] = it["rubric"]
        else:
            seen[key] = it
            out.append(it)
    return out


def save_ops(level, pool):
    lines = ["# 人工智能训练师（%s级）操作技能题库" % ("三" if str(level) == "3" else "四")]
    for it in pool:
        lines.append("## %s %s" % (it["code"] or "-", it["name"]))
        if it.get("time"):
            lines.append("- 考核时间：%s" % it["time"])
        if it.get("score"):
            lines.append("- 配分：%s分" % it["score"])
        for label, key in (("场地设备要求", "site"), ("工作任务", "task"),
                           ("技能要求", "skill"), ("质量指标", "quality")):
            if it.get(key):
                lines.append("### %s" % label)
                lines.append(it[key])
        if it.get("rubric"):
            lines.append("### 评分表")
            for r in it["rubric"]:
                lines.append("%s|%d|%s" % (r["id"], r["score"], r["desc"]))
        if it.get("answers"):
            lines.append("### 参考答案")
            lines.append("```text")
            lines.append(it["answers"])
            lines.append("```")
    path = os.path.join(lib.DATA, "ops-%s.md" % level)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- 主流程
DEFAULT = {
    "3": {"dir": "/Users/tony/Downloads/4-04-05-05_3_20250701", "cn": "三",
          "bank": "第3部分-人工智能训练师_3级_理论知识复习题.docx",
          "ops": "第4部分_人工智能训练师_3级_操作技能复习题.doc",
          "mock": "第5部分_人工智能训练师_3级_理论知识模拟试卷.docx",
          "opsmock": "第6部分_人工智能训练师_3级_操作技能模拟试卷.doc"},
    "4": {"dir": "/Users/tony/Downloads/4-04-05-05_4_20250701", "cn": "四",
          "bank": "第3部分-人工智能训练师_4级_理论知识复习题.docx",
          "ops": "第4部分_人工智能训练师_4级_操作技能复习题.doc",
          "mock": "第5部分_人工智能训练师_4级_理论知识模拟试卷.docx",
          "opsmock": "第6部分_人工智能训练师_4级_操作技能模拟试卷.doc"},
}


def build_theory(level, bank_path, mock_path, orig_bytes):
    bank_sec = parse_theory(paragraphs(bank_path))
    mock_sec, ans = {}, {}
    if mock_path and os.path.exists(mock_path):
        mock_sec = parse_theory(paragraphs(mock_path))
        ans = parse_answers(paragraphs(mock_path))

    # 编号连续化 + 答案回填（按题干归一化匹配）
    merged = {"level": str(level),
              "title": "人工智能训练师（%s级）理论知识题库" % DEFAULT[str(level)]["cn"],
              "sections": {}}
    stat = {}
    for t in lib.TYPES:
        qs = bank_sec.get(t) or []
        idx = {norm(q["stem"]): q for q in qs}
        for q in (mock_sec.get(t) or []):
            tgt = idx.get(norm(q["stem"]))
            if tgt is None:
                qs.append(dict(q, n=len(qs) + 1))
                idx[norm(q["stem"])] = qs[-1]
        # 答案：先用本卷答案（按模拟卷题号）
        official = 0
        for n, a in (ans.get(t) or {}).items():
            src = next((q for q in (mock_sec.get(t) or []) if q["n"] == n), None)
            if not src:
                continue
            tgt = idx.get(norm(src["stem"]))
            if tgt is not None and not tgt["ans"]:
                tgt["ans"] = a
                official += 1
        for i, q in enumerate(qs, 1):
            q["n"] = i
        merged["sections"][t] = qs
        stat[t] = {"total": len(qs), "answered": sum(1 for q in qs if q["ans"])}
    lib.save_bank(merged)

    paper = None
    if mock_sec:
        sec_ids = []
        for t in lib.TYPES:
            qs = merged["sections"][t]
            idx = {norm(q["stem"]): q["n"] for q in qs}
            ids = [idx[norm(q["stem"])] for q in (mock_sec.get(t) or []) if norm(q["stem"]) in idx]
            if ids:
                sec_ids.append({"type": t, "ids": ids})
        paper = {"id": "official-%s-theory" % level, "level": str(level), "kind": "theory",
                 "name": "人工智能训练师（%s级）理论知识试卷" % DEFAULT[str(level)]["cn"],
                 "source": "官方模拟卷", "sections": sec_ids}
    return merged, paper, stat


def build_ops(level, pool_path, mock_path):
    pool = parse_ops(paragraphs(pool_path))
    pool = dedupe_ops(pool)
    if mock_path and os.path.exists(mock_path):
        merge_ops(pool, parse_ops(paragraphs(mock_path)))
        pool = dedupe_ops(pool)
    save_ops(level, pool)
    return pool


def build_composition(level, mock_path):
    """从官方模拟卷的题型抬头还原组卷规则：题型、题量、每题分、共分、考试时间"""
    paras = paragraphs(mock_path) if mock_path and os.path.exists(mock_path) else []
    secs, tm = [], "90min"
    for ln in paras:
        m = re.match(r"考试时间[：:]\s*(\d+)\s*min", ln)
        if m:
            tm = m.group(1) + "min"
            continue
        m = re.match(r"^(?:[一二三四五六七八九十]+、\s*)?(判断题|单选题|多选题)\s*[（(](.*)[）)]\s*$", ln)
        if not m:
            continue
        desc = m.group(2)
        each = re.search(r"每题\s*([\d.]+)\s*分", desc)
        tot = re.search(r"共\s*(\d+)\s*分", desc)
        secs.append({"type": m.group(1),
                     "each": float(each.group(1)) if each else 0.5,
                     "total": float(tot.group(1)) if tot else 0,
                     "desc": re.sub(r"每题.*$", "", desc).strip()})
    b = lib.load_bank(level)
    for s_ in secs:
        n = len(b["sections"].get(s_["type"]) or [])
        if not s_["total"]:
            s_["total"] = s_["each"] * n
        s_["count"] = int(round(s_["total"] / s_["each"]))
    return {"name": "人工智能训练师（%s级）理论知识试卷" % DEFAULT[str(level)]["cn"],
            "time": tm, "sections": secs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rebuild", "theory", "ops"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--level")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--src3", default=DEFAULT["3"]["dir"])
    ap.add_argument("--src4", default=DEFAULT["4"]["dir"])
    a = ap.parse_args()

    if a.cmd == "rebuild":
        comp = {"theory": {}, "ops": {}}
        manifest = {"built_at": time.strftime("%Y-%m-%d %H:%M"), "levels": {},
                    "sources": {}, "papers": []}
        orig_total = 0
        for lv in ("3", "4"):
            d = a.src3 if lv == "3" else a.src4
            cfg = DEFAULT[lv]
            paths = {k: os.path.join(d, cfg[k]) for k in ("bank", "ops", "mock", "opsmock")}
            for p in paths.values():
                if os.path.exists(p):
                    orig_total += os.path.getsize(p)
            merged, paper, stat = build_theory(lv, paths["bank"], paths["mock"], 0)
            pool = build_ops(lv, paths["ops"], paths["opsmock"])
            manifest["levels"][lv] = {"theory": stat, "ops": len(pool)}
            manifest["sources"][lv] = {k: os.path.basename(v) for k, v in paths.items()}
            if paper:
                manifest["papers"].append(paper)
            manifest["papers"].append(build_ops_paper(lv, pool, paths["opsmock"]))
            comp.setdefault("theory", {})[lv] = build_composition(lv, paths["mock"])
        for lv, pool in (("3", lib.load_ops("3")), ("4", lib.load_ops("4"))):
            op = next((x for x in manifest["papers"] if x["id"] == "official-%s-ops" % lv), None)
            if op:
                comp["ops"][lv] = {"name": op["name"], "slots": op["slots"]}
        lib.save_json(os.path.join(lib.DATA, "composition.json"), comp)

        md_total = sum(os.path.getsize(os.path.join(lib.DATA, f))
                       for f in os.listdir(lib.DATA) if f.endswith(".md"))
        manifest["size"] = {"source_bytes": orig_total, "md_bytes": md_total}
        lib.save_json(os.path.join(lib.DATA, "manifest.json"), manifest)
        print("重建完成：", json.dumps(manifest["size"], ensure_ascii=False),
              json.dumps(manifest["levels"], ensure_ascii=False))
        return

    if not a.path or not a.level:
        raise SystemExit("需要 --level 与文件路径")
    if a.cmd == "theory":
        bank = lib.load_bank(a.level) if a.append else {
            "level": a.level, "title": "人工智能训练师（%s级）理论知识题库" %
            DEFAULT[a.level]["cn"], "sections": {t: [] for t in lib.TYPES}}
        new = parse_theory(paragraphs(a.path))
        for t in lib.TYPES:
            have = {norm(q["stem"]) for q in bank["sections"][t]}
            for q in new.get(t, []):
                if norm(q["stem"]) not in have:
                    bank["sections"][t].append(q)
            for i, q in enumerate(bank["sections"][t], 1):
                q["n"] = i
        lib.save_bank(bank)
        print("已写入", {t: len(v) for t, v in bank["sections"].items()})
    else:
        pool = dedupe_ops(lib.load_ops(a.level)) if a.append else []
        merge_ops(pool, parse_ops(paragraphs(a.path)))
        pool = dedupe_ops(pool)
        save_ops(a.level, pool)
        print("已写入操作技能试题", len(pool), "道")


def build_ops_paper(level, pool, mock_path):
    """官方操作技能模拟卷：题目清单 + 配分 + 时间"""
    slots = []
    if mock_path and os.path.exists(mock_path):
        for it in parse_ops(paragraphs(mock_path)):
            if it.get("score"):
                slots.append({"code": it["code"], "name": it["name"],
                              "score": int(it["score"]), "time": it["time"]})
    # 只保留确实存在于题库的
    names = {it["name"] for it in pool}
    seen, uniq = set(), []
    for s in slots:
        key = s["code"] or s["name"]
        if s["name"] in names and key not in seen:
            seen.add(key)
            uniq.append(s)
    slots = uniq
    return {"id": "official-%s-ops" % level, "level": str(level), "kind": "ops",
            "name": "人工智能训练师（%s级）操作技能考核" % DEFAULT[str(level)]["cn"],
            "source": "官方模拟卷", "slots": slots}


if __name__ == "__main__":
    main()
