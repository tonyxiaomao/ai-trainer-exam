#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地练习页面：在浏览器里点选作答，提交后即时判分。

两种模式：
    batch  —— 按题型顺序刷某一区间，例如 三级判断题第 1-20 题
    random —— 跨题型随机抽 N 题，可指定种子复现同一套题

用法：
    python3 scripts/web.py --level 3 --type 判断题 --from 1 --to 20
    python3 scripts/web.py --level 3 --mode random --n 20
    python3 scripts/web.py --level 4 --mode random --n 30 --types 判断题,单选题 --seed 7

判分优先级：corrections.json（已确认）> 题库官方答案 > ai-judgments.json（AI 判定，页面标注）
三者都没有的题，提交后显示“待判定”，由对话里的 AI 给结论。
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

AI_JUDGE = os.path.join(lib.RECORDS, "ai-judgments.json")
LATEST = os.path.join(lib.RECORDS, "submissions", "latest.json")
CN_LEVEL = {"3": "三", "4": "四"}
EACH = {"判断题": 0.5, "单选题": 0.5, "多选题": 1.0}


# ---------------------------------------------------------------- 取题
def answer_index(level):
    """返回 (bank, {(题型, 题号): {ans, src, note}})"""
    bank = lib.apply_corrections(lib.load_bank(level))
    ai = lib.load_json(AI_JUDGE, {})
    idx = {}
    for t, qs in bank["sections"].items():
        for q in qs:
            k = "%s:%s:%d" % (level, t, q["n"])
            note = (ai.get(k) or {}).get("note", "")
            if (q.get("ans") or "").strip():
                idx[(t, q["n"])] = {"ans": q["ans"].strip(), "src": "official", "note": note}
            elif (ai.get(k) or {}).get("ans"):
                idx[(t, q["n"])] = {"ans": ai[k]["ans"], "src": "ai", "note": note}
    return bank, idx


def pack(t, q, a, no, each=None):
    a = a or {}
    it = {"no": no, "n": q["n"], "t": t, "stem": q["stem"], "opts": q.get("opts") or {},
          "ans": a.get("ans", ""), "src": a.get("src", ""), "note": a.get("note", "")}
    if each is not None:
        it["each"] = each
    return it


def items_batch(level, type_name, start, end):
    bank, idx = answer_index(level)
    out = []
    for q in bank["sections"].get(type_name) or []:
        if start <= q["n"] <= end:
            out.append(pack(type_name, q, idx.get((type_name, q["n"])), q["n"]))
    return out


def items_random(level, types, n, seed, graded=False):
    bank, idx = answer_index(level)
    pool = [(t, q) for t in types for q in (bank["sections"].get(t) or [])]
    if not pool:
        return []
    rng = random.Random(seed)
    if graded:
        have = [x for x in pool if idx.get((x[0], x[1]["n"]))]
        rest = [x for x in pool if not idx.get((x[0], x[1]["n"]))]
        pick = rng.sample(have, min(n, len(have)))
        if len(pick) < n:
            pick += rng.sample(rest, min(n - len(pick), len(rest)))
    else:
        pick = rng.sample(pool, min(n, len(pool)))
    # 按官方卷的题型顺序排列（判断 → 单选 → 多选），同题型内按原题号
    pick.sort(key=lambda x: (types.index(x[0]), x[1]["n"]))
    return [pack(t, q, idx.get((t, q["n"])), i + 1) for i, (t, q) in enumerate(pick)]


def types_of(level):
    bank = lib.load_bank(level)
    return [t for t in lib.TYPES if bank["sections"].get(t)]


def total_of(level, type_name):
    return len(lib.load_bank(level)["sections"].get(type_name) or [])


# ---------------------------------------------------------------- 模拟卷
def comp_of(level):
    c = lib.load_json(os.path.join(lib.DATA, "composition.json"), {})
    try:
        return c["theory"][str(level)]
    except KeyError:
        raise SystemExit("data/composition.json 缺少 %s 级理论卷组卷规则" % level)


def gradable_count(level, type_name):
    bank, idx = answer_index(level)
    return sum(1 for q in (bank["sections"].get(type_name) or [])
               if idx.get((type_name, q["n"])))


def items_exam(level, seed, graded=False):
    """按官方卷的题型/题量/配分随机组卷；题号全卷连续，含分节信息"""
    bank, idx = answer_index(level)
    c = comp_of(level)
    rng = random.Random(seed)
    items, no = [], 0
    for i, sec in enumerate(c["sections"]):
        t = sec["type"]
        pool = bank["sections"].get(t) or []
        cand = [q for q in pool if idx.get((t, q["n"]))] if graded else list(pool)
        if not cand:
            continue
        pick = rng.sample(cand, min(sec["count"], len(cand)))
        pick.sort(key=lambda q: q["n"])
        label = "%s、%s" % ("一二三四五六"[i], t)
        for q in pick:
            no += 1
            items.append(pack(t, q, idx.get((t, q["n"])), no, each=sec["each"]))
            items[-1]["sec"] = label
    return items


def exam_summary(level):
    c = comp_of(level)
    parts = ["%s %d 题" % (s["type"], s["count"]) for s in c["sections"]]
    return "　+　".join(parts)


# ---------------------------------------------------------------- 判分
def each_of(it):
    return it.get("each") or EACH.get(it["t"], 0.5)


def grade(items, answers):
    rows, right, gradable = [], 0, 0
    for it in items:
        u = (answers.get(str(it["no"])) or "").strip()
        ok = None
        if it["ans"]:
            gradable += 1
            if u:
                ok, _ = lib.grade_one({"ans": it["ans"], "opts": it["opts"]}, u)
                if ok:
                    right += 1
        row = {"no": it["no"], "n": it["n"], "t": it["t"], "user": u,
               "ans": it["ans"], "src": it["src"], "ok": ok, "note": it["note"],
               "each": each_of(it)}
        if it.get("sec"):
            row["sec"] = it["sec"]
        rows.append(row)
    full = sum(each_of(it) for it in items if it["ans"])
    score = sum(r["each"] for r in rows if r["ok"] is True)
    return {"rows": rows, "right": right, "gradable": gradable,
            "answered": sum(1 for r in rows if r["user"]),
            "total": len(rows), "score": round(score, 1), "full": round(full, 1),
            "mode": "", "kind": ""}


def save_record(rng, items, answers, res):
    kind = "模拟卷" if rng["mode"] == "exam" else ("随机练习" if rng["mode"] == "random" else rng["type"])
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "level": rng["level"],
           "mode": rng["mode"], "type": kind, "from": rng["start"], "to": rng["end"],
           "n": rng["n"], "seed": rng["seed"], "answers": answers,
           "score": res["score"], "full": res["full"], "right": res["right"],
           "gradable": res["gradable"], "total": res["total"],
           "pending": [r["no"] for r in res["rows"] if not r["ans"] and r["user"]]}
    lib.save_json(LATEST, rec)

    hist_path = os.path.join(lib.RECORDS, "history.json")
    hist = lib.load_json(hist_path, [])
    hist.append({"ts": rec["ts"], "level": rng["level"], "mode": rng["mode"],
                 "type": kind, "right": res["right"], "total": res["answered"],
                 "score": res["score"], "full": res["full"], "page": True})
    lib.save_json(hist_path, hist)

    wb_path = os.path.join(lib.RECORDS, "wrongbook.json")
    wb = lib.load_json(wb_path, {})
    for r in res["rows"]:
        if r["ok"] is False:
            it = next(x for x in items if x["no"] == r["no"])
            wb["%s:%s:%d" % (rng["level"], r["t"], r["n"])] = {
                "level": rng["level"], "type": r["t"], "n": r["n"],
                "stem": it["stem"][:60], "user": r["user"], "ans": r["ans"], "ts": rec["ts"]}
    lib.save_json(wb_path, wb)


# ---------------------------------------------------------------- 页面
PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --bg:#f6f7f9; --card:#fff; --ink:#1b1f24; --sub:#6b7280; --line:#e6e8ec;
  --brand:#2f6df6; --brand-soft:#eaf0ff; --ok:#15803d; --ok-soft:#e9f7ee;
  --bad:#c62828; --bad-soft:#fdecec; --warn:#a16207; --warn-soft:#fdf6e3;
}
@media (prefers-color-scheme:dark){
  :root{--bg:#14161a;--card:#1c1f25;--ink:#e8eaed;--sub:#9aa3af;--line:#2b3038;
        --brand:#6f9bff;--brand-soft:#1e2a44;--ok:#5cc98b;--ok-soft:#16301f;
        --bad:#ff8a80;--bad-soft:#33191a;--warn:#e5b567;--warn-soft:#2e2617;}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:0 16px 130px}
header{position:sticky;top:0;z-index:9;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:12px 0 10px}
.hrow{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:650;letter-spacing:.2px}
.tag{font-size:12px;color:var(--sub);border:1px solid var(--line);border-radius:999px;padding:1px 9px}
.bar{flex:1;height:6px;background:var(--line);border-radius:99px;overflow:hidden;min-width:90px}
.bar>i{display:block;height:100%;width:0;background:var(--brand);transition:width .25s}
.count{font-size:13px;color:var(--sub);font-variant-numeric:tabular-nums}
.q{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:0 0 12px;
  transition:border-color .18s,background .18s}
.q.done{border-color:color-mix(in srgb,var(--brand) 35%,var(--line))}
.q.right{border-color:var(--ok);background:var(--ok-soft)}
.q.wrong{border-color:var(--bad);background:var(--bad-soft)}
.stem{display:flex;gap:10px;font-size:15.5px}
.no{color:var(--sub);font-variant-numeric:tabular-nums;min-width:2.6em;flex:0 0 auto;text-align:right}
.qtype{font-size:11.5px;color:var(--sub);border:1px solid var(--line);border-radius:6px;
  padding:0 5px;height:1.4em;line-height:1.35em;margin-left:6px;white-space:nowrap}
.opts{margin-top:10px;display:flex;flex-direction:column;gap:7px;padding-left:2.2em}
.opt{display:flex;gap:9px;align-items:flex-start;text-align:left;background:transparent;
  border:1px solid var(--line);border-radius:10px;padding:8px 11px;color:var(--ink);
  font:inherit;cursor:pointer;transition:.15s}
.opt:hover{border-color:var(--brand);background:var(--brand-soft)}
.opt .lt{color:var(--sub);font-weight:600;min-width:1.1em}
.opt.on{border-color:var(--brand);background:var(--brand-soft)}
.opt.on .lt{color:var(--brand)}
.judge{display:flex;gap:10px;padding-left:2.2em;margin-top:11px}
.jb{flex:0 0 auto;min-width:92px;padding:8px 0;border-radius:10px;border:1px solid var(--line);
  background:transparent;color:var(--ink);font:inherit;font-size:16px;cursor:pointer;transition:.15s}
.jb:hover{border-color:var(--brand);background:var(--brand-soft)}
.jb.on{border-color:var(--brand);background:var(--brand-soft);color:var(--brand);font-weight:650}
.res{margin-top:10px;padding-left:2.2em;font-size:14px;display:none}
.res.show{display:block}
.ok{color:var(--ok)} .no-{color:var(--bad)} .wait{color:var(--warn)}
.ans-ok{border-color:var(--ok)!important;background:var(--ok-soft)!important;color:var(--ok)!important;font-weight:650}
.ans-bad{border-color:var(--bad)!important;background:var(--bad-soft)!important;color:var(--bad)!important;font-weight:650}
.badge{display:inline-block;font-size:11.5px;border-radius:6px;padding:0 6px;margin-left:6px;vertical-align:1px}
.b-official{background:var(--ok-soft);color:var(--ok)}
.b-ai{background:var(--warn-soft);color:var(--warn)}
.note{color:var(--sub);font-size:13.5px;margin-top:4px}
footer{position:fixed;left:0;right:0;bottom:0;background:color-mix(in srgb,var(--bg) 92%,transparent);
  backdrop-filter:blur(10px);border-top:1px solid var(--line);padding:11px 0}
.fwrap{max-width:820px;margin:0 auto;padding:0 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button.act{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;
  padding:9px 15px;font:inherit;font-size:14px;cursor:pointer;transition:.15s}
button.act:hover{border-color:var(--brand);color:var(--brand)}
button.act.primary{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:600}
button.act.primary:hover{filter:brightness(1.06);color:#fff}
.sum{flex:1;font-size:13.5px;color:var(--sub);min-width:150px}
.sum b{color:var(--ink);font-size:15px}
.kbd{font-size:12px;color:var(--sub);border:1px solid var(--line);border-radius:5px;padding:0 5px;margin:0 1px}
.nav{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:14px 0}
.nav a{color:var(--sub);text-decoration:none;border:1px solid var(--line);background:var(--card);
  border-radius:9px;padding:5px 11px;transition:.15s}
.nav a:hover{border-color:var(--brand);color:var(--brand)}
.nav a.on{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:600}
.nav .sp{flex:1}
.nav .dim{color:var(--sub);opacity:.45;border-style:dashed}
.crumb{display:flex;gap:7px;align-items:center;flex-wrap:wrap;font-size:12.5px;color:var(--sub);margin:10px 0 0}
.crumb a{color:var(--sub);text-decoration:none;border-bottom:1px dashed var(--line);padding-bottom:1px}
.crumb a:hover{color:var(--brand);border-color:var(--brand)}
.crumb b{color:var(--ink);font-weight:600}
.crumb .sep{opacity:.5}
.sec{display:flex;align-items:baseline;gap:9px;margin:26px 0 12px;padding-left:10px;
  border-left:3px solid var(--brand);font-size:15px;font-weight:650}
.sec small{font-weight:400;color:var(--sub);font-size:12.5px}
.tmr{font-size:13px;color:var(--sub);border:1px solid var(--line);border-radius:8px;
  padding:1px 9px;font-variant-numeric:tabular-nums}
.tmr.warn{color:var(--bad);border-color:var(--bad);font-weight:650}
@media (max-width:560px){.stem{font-size:15px}.judge{padding-left:0}.opts{padding-left:0}.res{padding-left:0}}
</style>
</head>
<body>
<header><div class="wrap" style="padding-bottom:0"><div class="hrow">
  <h1>__TITLE__</h1><span class="tag" id="tag">__SUBTITLE__</span>
  <div class="bar"><i id="bar"></i></div><span class="count" id="count">0/0</span>
  <span class="tmr" id="tmr" style="display:none"></span>
</div></div></header>

<div class="wrap" style="padding-bottom:0"><div class="crumb">__CRUMB__</div></div>
<div class="wrap" style="padding-bottom:0"><div class="nav">__NAV__</div></div>

<div class="wrap" id="list"></div>

<footer><div class="fwrap">
  <div class="sum" id="sum"></div>
  <button class="act" id="reset">重做</button>
  <button class="act" id="copy">复制作答</button>
  <button class="act primary" id="submit">提交判分</button>
</div></footer>

<script>
const DATA = __DATA__;
const QS = DATA.items, MODE = DATA.mode, EXAM = DATA.exam || null;
const ans = {}; let graded = null;

const list = document.getElementById('list');
const bar = document.getElementById('bar');
const countEl = document.getElementById('count');
const sumEl = document.getElementById('sum');

function isJ(q){ return q.t === '判断题'; }
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function render(){
  list.innerHTML = '';
  let secIdx = 0, lastSec = null;
  QS.forEach((q, i) => {
    if (q.sec && q.sec !== lastSec){
      lastSec = q.sec;
      const head = document.createElement('div');
      head.className = 'sec'; head.id = 'sec' + (secIdx++);
      const cnt = QS.filter(x => x.sec === q.sec).length;
      head.innerHTML = q.sec + '<small>共 ' + cnt + ' 题 · 每题 ' + (q.each || 0.5) + ' 分</small>';
      list.appendChild(head);
    }
    const card = document.createElement('div');
    card.className = 'q'; card.id = 'q' + q.no;
    const head = document.createElement('div');
    head.className = 'stem';
    head.innerHTML = '<span class="no">' + q.no + '.</span><span>' + esc(q.stem) +
      (MODE === 'random' ? '<span class="qtype">' + q.t + ' 原题#' + q.n + '</span>' : '') + '</span>';
    card.appendChild(head);

    if (isJ(q)){
      const box = document.createElement('div'); box.className = 'judge';
      [['√','对'],['×','错']].forEach(([v, label]) => {
        const b = document.createElement('button');
        b.className = 'jb'; b.dataset.v = v; b.dataset.no = q.no;
        b.textContent = v + '  ' + label;
        b.onclick = () => pick(q.no, v, false);
        box.appendChild(b);
      });
      card.appendChild(box);
    } else {
      const box = document.createElement('div'); box.className = 'opts';
      Object.keys(q.opts).sort().forEach(k => {
        const b = document.createElement('button');
        b.className = 'opt'; b.dataset.k = k; b.dataset.no = q.no;
        b.innerHTML = '<span class="lt">' + k + '</span><span>' + esc(q.opts[k]) + '</span>';
        b.onclick = () => pick(q.no, k, q.t === '多选题');
        box.appendChild(b);
      });
      card.appendChild(box);
    }

    const res = document.createElement('div'); res.className = 'res'; res.id = 'r' + q.no;
    card.appendChild(res);
    list.appendChild(card);
  });
  paint(); refresh();
}

function pick(no, v, multi){
  if (graded) return;
  if (multi){
    const cur = (ans[no] || '').split('').filter(Boolean);
    const i = cur.indexOf(v);
    if (i >= 0) cur.splice(i,1); else { cur.push(v); cur.sort(); }
    if (cur.length) ans[no] = cur.join(''); else delete ans[no];
  } else {
    if (ans[no] === v) delete ans[no]; else ans[no] = v;
  }
  paint(); refresh();
  const next = QS.find(q => !ans[q.no]);
  if (next) document.getElementById('q' + next.no).scrollIntoView({behavior:'smooth', block:'center'});
}

function paint(){
  document.querySelectorAll('.jb,.opt').forEach(b => {
    const v = b.dataset.v || b.dataset.k;
    b.classList.toggle('on', (ans[b.dataset.no] || '').includes(v));
  });
  document.querySelectorAll('.q').forEach(c => {
    c.classList.toggle('done', !!ans[c.id.slice(1)]);
  });
}

function refresh(){
  const done = Object.keys(ans).length;
  countEl.textContent = done + '/' + QS.length;
  bar.style.width = (100 * done / QS.length) + '%';
}

document.getElementById('reset').onclick = () => {
  graded = null; Object.keys(ans).forEach(k => delete ans[k]);
  render(); hint();
};
document.getElementById('copy').onclick = () => {
  const s = QS.filter(q => ans[q.no]).map(q => q.no + ':' + ans[q.no]).join(',');
  navigator.clipboard.writeText(s).then(
    () => sumEl.textContent = '作答串已复制：' + s.slice(0, 70) + (s.length > 70 ? '…' : ''),
    () => sumEl.textContent = s);
};

document.getElementById('submit').onclick = async () => {
  if (EXAM && !graded){
    const left = QS.length - Object.keys(ans).length;
    if (left > 0 && !confirm('还有 ' + left + ' 题未作答，确定交卷？')) return;
  }
  const body = JSON.stringify({answers: ans, level: DATA.level, mode: MODE,
    type: DATA.type, from: DATA.from, to: DATA.to, n: DATA.n, seed: DATA.seed,
    graded: DATA.graded});
  const r = await fetch('/api/submit', {method:'POST', headers:{'Content-Type':'application/json'}, body});
  const res = await r.json();
  graded = res; show(res);
};

function show(res){
  res.rows.forEach(row => {
    const card = document.getElementById('q' + row.no);
    const box = document.getElementById('r' + row.no);
    if (!card) return;
    const mine = row.user ? row.user.split('').join('') : '—';
    if (!row.user){ box.className = 'res show'; box.innerHTML = '<span class="wait">未作答</span>'; return; }
    if (row.ok === true){
      card.classList.add('right'); box.className = 'res show';
      box.innerHTML = '<span class="ok"><b>✔ 正确</b></span>' + badge(row) +
        (row.note ? '<div class="note">' + esc(row.note) + '</div>' : '');
    } else if (row.ok === false){
      card.classList.add('wrong'); box.className = 'res show';
      box.innerHTML = '<span class="no-"><b>✘ 错</b></span>　你答 <b>' + mine + '</b>，正确 <b>' +
        row.ans + '</b>' + badge(row) + (row.note ? '<div class="note">' + esc(row.note) + '</div>' : '');
    } else {
      box.className = 'res show';
      box.innerHTML = '<span class="wait">已记录（' + mine + '）· 原卷无答案，回对话里我逐题判定</span>';
    }
    if (row.ans) card.querySelectorAll('.jb,.opt').forEach(b => {
      const v = b.dataset.v || b.dataset.k;
      if (row.ans.includes(v)) b.classList.add('ans-ok');
      else if (row.user && row.user.includes(v)) b.classList.add('ans-bad');
    });
  });
  const pend = res.rows.filter(r => !r.ans && r.user).length;
  let tail = '';
  if (EXAM && res.full > 0 && res.full < 99.9){
    tail = '　<span>按可判题折算 <b>' + Math.round(100 * res.score / res.full) + '</b> / 100</span>';
  }
  sumEl.innerHTML = '得分 <b>' + res.score + ' / ' + res.full + '</b>　答对 ' + res.right + '/' +
    res.gradable + (pend ? '　<span class="wait">另有 ' + pend + ' 题待 AI 判定</span>' : '') + tail;
  window.scrollTo({top:0, behavior:'smooth'});
}

function badge(row){
  return row.src === 'ai' ? '<span class="badge b-ai">AI 判定·非官方</span>'
                          : '<span class="badge b-official">官方答案</span>';
}

function hint(){
  const one = new Set(QS.map(q => q.t));
  if (MODE === 'random' || one.size > 1){
    sumEl.innerHTML = '点选作答，也可按 <span class="kbd">1</span>/<span class="kbd">2</span> 判对错、<span class="kbd">A</span>~<span class="kbd">E</span> 选选项';
    return;
  }
  const t = QS.length ? QS[0].t : '判断题';
  sumEl.innerHTML = t === '判断题'
    ? '点选作答，也可按 <span class="kbd">1</span> 对 / <span class="kbd">2</span> 错'
    : '点选项作答，也可按 <span class="kbd">A</span>~<span class="kbd">E</span>' + (t === '多选题' ? '（可多选）' : '');
}

document.addEventListener('keydown', e => {
  if (graded || e.metaKey || e.ctrlKey) return;
  const k = e.key.toUpperCase();
  const next = QS.find(q => !ans[q.no]);
  if (!next) return;
  if (isJ(next) && (k === '1' || k === '2')){ pick(next.no, k === '1' ? '√' : '×', false); e.preventDefault(); }
  else if (!isJ(next) && 'ABCDE'.includes(k)){ pick(next.no, k, next.t === '多选题'); e.preventDefault(); }
});

function startTimer(sec){
  const el = document.getElementById('tmr');
  let left = sec;
  const tick = () => {
    if (graded){ el.textContent = '已交卷'; return; }
    const m = Math.floor(left / 60), s = left % 60;
    el.textContent = '⏱ ' + m + ':' + (s < 10 ? '0' : '') + s;
    el.classList.toggle('warn', left <= 300);
    if (left <= 0){
      el.textContent = '⏱ 时间到';
      sumEl.textContent = '考试时间到，正在自动交卷…';
      document.getElementById('submit').click();
      return;
    }
    left -= 1;
    setTimeout(tick, 1000);
  };
  tick();
}

if (EXAM){
  document.getElementById('submit').textContent = '交卷';
  document.getElementById('tmr').style.display = '';
  startTimer(EXAM.minutes * 60);
}
hint(); render();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- 首页与二级入口
BASE_CSS = r"""
:root{--bg:#f6f7f9;--card:#fff;--ink:#1b1f24;--sub:#6b7280;--line:#e6e8ec;
  --brand:#2f6df6;--brand-soft:#eaf0ff;--ok:#15803d;--warn:#a16207;--warn-soft:#fdf6e3}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--card:#1c1f25;--ink:#e8eaed;--sub:#9aa3af;
  --line:#2b3038;--brand:#6f9bff;--brand-soft:#1e2a44;--ok:#5cc98b;--warn:#e5b567;--warn-soft:#2e2617}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:34px 18px 64px}
.top{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
h1{font-size:19px;margin:0;font-weight:700;letter-spacing:.2px}
.lv{display:flex;gap:8px}
.lv a{font-size:13.5px;text-decoration:none;color:var(--sub);border:1px solid var(--line);
  background:var(--card);border-radius:999px;padding:4px 15px;transition:.15s}
.lv a:hover{border-color:var(--brand);color:var(--brand)}
.lv a.on{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:650}
.lead{color:var(--sub);font-size:13.5px;margin:10px 0 0}
.lead b{color:var(--ink)}
.step{font-size:12.5px;color:var(--sub);letter-spacing:.08em;margin:28px 0 10px}
.grid{display:flex;flex-direction:column;gap:13px}
.card{display:flex;gap:16px;align-items:flex-start;background:var(--card);border:1px solid var(--line);
  border-radius:16px;padding:18px 20px;transition:.18s;text-decoration:none;color:inherit}
.card.link:hover{border-color:var(--brand);box-shadow:0 8px 24px rgba(47,109,246,.10);transform:translateY(-1px)}
.ic{font-size:23px;line-height:1.3;flex:0 0 auto;width:30px;text-align:center}
.card h3{margin:0 0 2px;font-size:16px;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.card h3 small{font-size:12.5px;color:var(--sub);font-weight:400}
.card p{margin:3px 0 0;color:var(--sub);font-size:13.5px;line-height:1.7}
.go{margin-left:auto;align-self:center;color:var(--brand);font-size:13.5px;white-space:nowrap;flex:0 0 auto}
.btns{margin-left:auto;display:flex;flex-direction:column;gap:7px;flex:0 0 auto;align-self:center}
.b{display:inline-block;text-decoration:none;text-align:center;font-size:13px;border:1px solid var(--line);
  border-radius:9px;padding:5px 13px;color:var(--ink);background:var(--card);white-space:nowrap;transition:.15s}
.b:hover{border-color:var(--brand);color:var(--brand)}
.b.primary{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:600}
.b.primary:hover{filter:brightness(1.06);color:#fff}
table.comp{width:100%;border-collapse:collapse;font-size:13.5px}
table.comp th,table.comp td{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left}
table.comp th{color:var(--sub);font-weight:500;font-size:12.5px}
table.comp td.num,table.comp th.num{text-align:right;font-variant-numeric:tabular-nums}
table.comp tr:last-child td{border-bottom:none;font-weight:600}
.foot{margin-top:26px;border-top:1px solid var(--line);padding-top:13px;color:var(--sub);
  font-size:13px;display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.foot b{color:var(--ink)}
.tag{font-size:11.5px;color:var(--sub);border:1px solid var(--line);border-radius:999px;padding:0 8px;font-weight:400}
.warnbox{margin-top:14px;font-size:13px;color:var(--warn);background:var(--warn-soft);
  border-radius:11px;padding:10px 13px;line-height:1.7}
@media (max-width:600px){.card{flex-wrap:wrap}.btns{margin-left:0;flex-direction:row;width:100%}.go{margin-left:0}}
"""

HOME = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>人工智能训练师（三级/四级）· 刷题入口</title>
<style>__CSS__</style></head><body><div class="wrap">
<div class="top"><h1>人工智能训练师考级练习</h1><div class="lv">__LVLINKS__</div></div>
<p class="lead">当前 <b>__LV__级</b>　题库共 <b>__TOTAL__</b> 题（判断 __J__ · 单选 __S__ · 多选 __M__）</p>
<div class="step">第二步 · 选择刷题方式<span style="letter-spacing:0;margin-left:8px;opacity:.8">（级别在右上角切换）</span></div>
<div class="grid">
  <a class="card link" href="?mode=bank&amp;level=__L__">
    <div class="ic">📚</div>
    <div><h3>完整题库 <span class="tag">全部 __TOTAL__ 题</span></h3>
      <p>按题型从头刷到尾，__SIZE__ 题一组，可前后翻组、随时提交判分。想系统过一遍就选这个。</p></div>
    <span class="go">进入 ›</span>
  </a>
  <a class="card link" href="?mode=exam&amp;level=__L__">
    <div class="ic">📝</div>
    <div><h3>模拟考题 <span class="tag">__N__ 题 · 100 分 · __MIN__ 分钟</span></h3>
      <p>按官方卷构成随机组卷：__COMP__。倒计时交卷即出分，错题自动进错题本。</p></div>
    <span class="go">进入 ›</span>
  </a>
</div>
<div class="foot"><span>累计练习 <b>__SESS__</b> 次</span><span>错题本 <b>__WRONG__</b> 道</span>
  <span>最近一次：__LAST__</span></div>
</div></body></html>"""

BANK = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__LV__级 · 完整题库</title>
<style>__CSS__</style></head><body><div class="wrap">
<div class="top"><h1>__LV__级 · 完整题库</h1><div class="lv">__LVLINKS__</div></div>
<p class="lead">共 <b>__TOTAL__</b> 题。选题型开始，每组 <b>__SIZE__</b> 题，做完在页面顶部点「下一组」接着往下刷。</p>
<div class="step">选择题型</div>
<div class="grid">__CARDS__</div>
<div class="foot"><a class="b" href="?">‹ 返回首页</a>
  <a class="b" href="?mode=exam&amp;level=__L__">直接做模拟考题 ›</a>
  <span>错题本 <b>__WRONG__</b> 道</span></div>
</div></body></html>"""

EXAM_INTRO = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__LV__级 · 模拟考题</title>
<style>__CSS__</style></head><body><div class="wrap">
<div class="top"><h1>__LV__级 · 模拟考题</h1><div class="lv">__LVLINKS__</div></div>
<p class="lead">按官方卷的题型、题量、配分随机组卷，满分 100 分，__MIN__ 分钟倒计时，交卷后逐题标答。</p>
<div class="step">卷面构成</div>
<div class="card"><div style="flex:1">
  <table class="comp"><tr><th>题型</th><th class="num">题量</th><th class="num">每题</th><th class="num">小计</th></tr>
  __ROWS__
  <tr><td>合计</td><td class="num">__N__</td><td class="num">—</td><td class="num">100 分</td></tr></table>
</div></div>
<div class="step">选择组卷方式</div>
<div class="grid">
  <a class="card link" href="?mode=exam&amp;level=__L__&amp;go=1&amp;graded=0">
    <div class="ic">🎲</div>
    <div><h3>全真模拟 · 全库随机</h3>
      <p>从整个题库抽题，覆盖面最广。但本级别带答案的题只有 __GRADED_ALL__ 道（约 __PCT__%），随机组卷后大约四分之一的题能机判，其余标「需 AI 判定」。</p></div>
    <span class="go">开考 ›</span>
  </a>
  <a class="card link" href="?mode=exam&amp;level=__L__&amp;go=1&amp;graded=1">
    <div class="ic">✅</div>
    <div><h3>全真模拟 · 只用有答案的题</h3>
      <p>只抽题库里有答案的题（判断 __GJ__ · 单选 __GS__ __GM__），整卷 100% 可自动判分，适合练手感、看真实分数。</p></div>
    <span class="go">开考 ›</span>
  </a>
</div>
<div class="warnbox">提示：两种方式都按官方卷顺序出题（判断 → 单选 → 多选），题号全卷连续；交卷后作答记录会存进错题本，可在对话里让我讲解错题。</div>
<div class="foot"><a class="b" href="?">‹ 返回首页</a><a class="b" href="?mode=bank&amp;level=__L__">先刷完整题库 ›</a></div>
</div></body></html>"""

GROUP = 20


def _hist():
    return lib.load_json(os.path.join(lib.RECORDS, "history.json"), [])


def _wrong_n():
    return len(lib.load_json(os.path.join(lib.RECORDS, "wrongbook.json"), {}))


def _qs(**kw):
    return urllib.parse.urlencode(kw)


def level_links(level, mode=""):
    out = []
    for lv in ("3", "4"):
        params = {"level": lv}
        if mode:
            params["mode"] = mode
        out.append('<a class="%s" href="?%s">%s级</a>'
                   % ("on" if lv == level else "", _qs(**params), CN_LEVEL[lv]))
    return "".join(out)


def _fill(html, pairs):
    for k, v in pairs.items():
        html = html.replace(k, str(v))
    return html


def page_home(level):
    bank = lib.load_bank(level)
    secs = {t: len(bank["sections"].get(t) or []) for t in lib.TYPES}
    c = comp_of(level)
    hist = _hist()
    return _fill(HOME, {
        "__CSS__": BASE_CSS, "__LVLINKS__": level_links(level),
        "__LV__": CN_LEVEL[level], "__L__": level,
        "__TOTAL__": sum(secs.values()), "__J__": secs.get("判断题", 0),
        "__S__": secs.get("单选题", 0), "__M__": secs.get("多选题", 0),
        "__N__": sum(s["count"] for s in c["sections"]),
        "__MIN__": str(c["time"]).replace("min", ""),
        "__COMP__": exam_summary(level),
        "__SESS__": len(hist), "__WRONG__": _wrong_n(),
        "__LAST__": hist[-1]["ts"] if hist else "还没练过", "__SIZE__": GROUP,
    })


def page_bank(level):
    bank = lib.load_bank(level)
    latest = lib.load_json(LATEST, {})
    cont = {}
    if str(latest.get("level")) == str(level) and latest.get("mode") == "batch":
        cont[latest.get("type")] = int(latest.get("to") or 0) + 1
    cards, num = [], "①②③④⑤"
    desc = {"判断题": "对 / 错 二选一，键盘 1 / 2 也能作答。",
            "单选题": "四个选项选一个，键盘 A~E 也能作答。",
            "多选题": "选全部正确项，少选多选都算错。"}
    for i, t in enumerate(types_of(level)):
        n = len(bank["sections"].get(t) or [])
        g = gradable_count(level, t)
        extra = "可自动判分 %d 题，其余标注待判定" % g if g < n else "全部可自动判分"
        btns = ['<a class="b primary" href="?%s">从第 1 题开始</a>'
                % _qs(mode="batch", level=level, type=t, **{"from": 1, "to": min(GROUP, n)})]
        s = cont.get(t)
        if s and s <= n:
            e = min(n, s + GROUP - 1)
            btns.append('<a class="b" href="?%s">继续 第%d–%d题</a>'
                        % (_qs(mode="batch", level=level, type=t, **{"from": s, "to": e}), s, e))
        cards.append(
            '<div class="card"><div class="ic">%s</div><div style="flex:1">'
            '<h3>%s <small>%d 题 · %s</small></h3><p>%s</p></div>'
            '<div class="btns">%s</div></div>'
            % (num[i], t, n, extra, desc.get(t, ""), "".join(btns)))
    return _fill(BANK, {
        "__CSS__": BASE_CSS, "__LVLINKS__": level_links(level, "bank"),
        "__LV__": CN_LEVEL[level], "__L__": level,
        "__TOTAL__": sum(len(bank["sections"].get(t) or []) for t in lib.TYPES),
        "__SIZE__": GROUP, "__CARDS__": "".join(cards),
        "__WRONG__": _wrong_n(),
    })


def page_exam_intro(level):
    c = comp_of(level)
    rows = "".join(
        "<tr><td>%s</td><td class='num'>%d</td><td class='num'>%g</td><td class='num'>%g</td></tr>"
        % (s["type"], s["count"], s["each"], s["total"]) for s in c["sections"])
    b = lib.load_bank(level)
    gj = gradable_count(level, "判断题")
    gs = gradable_count(level, "单选题")
    gm = gradable_count(level, "多选题")
    all_g = gj + gs + gm
    total = sum(len(b["sections"].get(t) or []) for t in lib.TYPES)
    return _fill(EXAM_INTRO, {
        "__CSS__": BASE_CSS, "__LVLINKS__": level_links(level, "exam"),
        "__LV__": CN_LEVEL[level], "__L__": level,
        "__MIN__": str(c["time"]).replace("min", ""),
        "__ROWS__": rows, "__N__": sum(s["count"] for s in c["sections"]),
        "__GRADED_ALL__": all_g, "__PCT__": int(round(100.0 * all_g / max(1, total))),
        "__GJ__": gj, "__GS__": gs,
        "__GM__": ("· 多选 %d" % gm) if gm else "",
    })


def _link(params, label, cls=""):
    return '<a class="%s" href="?%s">%s</a>' % (cls, urllib.parse.urlencode(params), label)


def nav_html(r, items=None):
    level, size = r["level"], max(1, r["end"] - r["start"] + 1)
    n = r["n"]
    parts = []
    if r["mode"] == "exam":
        secs = []
        for it in items or []:
            if it.get("sec") and it["sec"] not in secs:
                secs.append(it["sec"])
        for i, s in enumerate(secs):
            parts.append('<a href="#sec%d">%s</a>' % (i, s.split("、")[-1]))
        parts.append('<span class="sp"></span>')
        parts.append(_link({"mode": "exam", "level": level, "go": 1,
                            "graded": 1 if r.get("graded") else 0}, "换一套 ↻"))
        parts.append(_link({"mode": "exam", "level": level}, "试卷说明"))
        return "".join(parts)

    for t in types_of(level):
        on = "on" if (r["mode"] == "batch" and t == r["type"]) else ""
        parts.append(_link({"level": level, "mode": "batch", "type": t,
                            "from": 1, "to": size}, t, on))
    rand_on = "on" if (r["mode"] == "random" and not r["graded"]) else ""
    grad_on = "on" if (r["mode"] == "random" and r["graded"]) else ""
    parts.append(_link({"level": level, "mode": "random", "n": n}, "随机 %d 题" % n, rand_on))
    parts.append(_link({"level": level, "mode": "random", "n": n, "graded": 1},
                       "随机 %d 题·带答案" % n, grad_on))
    parts.append('<span class="sp"></span>')
    if r["mode"] == "batch":
        total = total_of(level, r["type"])
        if r["start"] > 1:
            parts.append(_link({"level": level, "mode": "batch", "type": r["type"],
                                "from": max(1, r["start"] - size), "to": r["start"] - 1}, "‹ 上一组"))
        else:
            parts.append('<a class="dim">‹ 上一组</a>')
        if r["end"] < total:
            parts.append(_link({"level": level, "mode": "batch", "type": r["type"],
                                "from": r["end"] + 1, "to": min(total, r["end"] + size)}, "下一组 ›"))
        else:
            parts.append('<a class="dim">下一组 ›</a>')
        parts.append('<span class="dim" style="border:none">本题型共 %d 题</span>' % total)
    else:
        parts.append(_link({"level": level, "mode": "random", "n": n, "graded": 1 if r["graded"] else 0},
                           "换一批 ↻"))
        parts.append('<span class="dim" style="border:none">%s · 跨题型</span>'
                     % ("只抽有官方/AI 答案的题" if r["graded"] else "全库随机"))
    return "".join(parts)


def crumb_html(r):
    level, mode = r["level"], r["mode"]
    cn = CN_LEVEL[level]
    parts = ['<a href="?">首页</a>']
    if mode == "batch":
        parts.append('<a href="?mode=bank&level=%s">完整题库</a>' % level)
        parts.append("<b>%s级 %s 第%d–%d题</b>" % (cn, r["type"], r["start"], r["end"]))
    elif mode == "random":
        parts.append("<b>%s级 随机 %d 题</b>" % (cn, r["n"]))
    elif mode == "exam":
        parts.append('<a href="?mode=exam&level=%s">模拟考题</a>' % level)
        parts.append("<b>%s级 模拟卷</b>" % cn)
    return '<span class="sep">›</span>'.join(parts)


def page_html(r, items):
    if r["mode"] == "exam":
        c = comp_of(r["level"])
        title = "人工智能训练师（%s级）· 模拟卷" % CN_LEVEL[r["level"]]
        exam = {"minutes": int(str(c["time"]).replace("min", "") or 90),
                "name": c["name"].replace("理论知识试卷", "理论知识模拟卷")}
    elif r["mode"] == "random":
        title = "人工智能训练师（%s级）· 随机抽题 %d 题" % (CN_LEVEL[r["level"]], len(items))
        exam = None
    else:
        title = "人工智能训练师（%s级）· %s 第%d–%d题" % (
            CN_LEVEL[r["level"]], r["type"], r["start"], r["end"])
        exam = None
    payload = {"level": r["level"], "mode": r["mode"], "type": r["type"],
               "from": r["start"], "to": r["end"], "n": r["n"], "seed": r["seed"],
               "graded": 1 if r.get("graded") else 0, "exam": exam,
               "items": items}
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = PAGE.replace("__DATA__", data).replace("__TITLE__", title)
    html = html.replace("__NAV__", nav_html(r, items))
    html = html.replace("__CRUMB__", crumb_html(r))
    total = sum(each_of(it) for it in items if it["ans"])
    graded = sum(1 for it in items if it["ans"])
    if r["mode"] == "exam":
        sub = "共 %d 题 · 满分 100 分 · %d 分钟" % (
            len(items), int(str(comp_of(r["level"])["time"]).replace("min", "") or 90))
        if graded < len(items):
            sub += " · 可判 %d 题" % graded
    else:
        sub = "共 %d 题 · 满分 %s 分" % (len(items), round(total, 1))
        if graded < len(items):
            sub += " · 可判 %d 题" % graded
    return html.replace("__SUBTITLE__", sub)


# ---------------------------------------------------------------- 路由
def parse_req(qs, default):
    def get(k, d=None):
        v = qs.get(k)
        if isinstance(v, list):
            v = v[0]
        return d if v in (None, "") else v

    level = get("level", default["level"])
    level = level if level in ("3", "4") else default["level"]
    types = types_of(level)
    mode = get("mode", default["mode"])
    mode = mode if mode in ("batch", "random", "exam", "bank", "home") else "batch"
    go = str(get("go", default.get("go", "0"))) in ("1", "true", "yes")

    size = max(1, default["end"] - default["start"] + 1)
    type_name = get("type", default["type"])
    if type_name not in types:
        type_name = types[0]
    try:
        start = int(get("from", 1))
    except ValueError:
        start = 1
    total = total_of(level, type_name)
    try:
        end = int(get("to", start + size - 1))
    except ValueError:
        end = start + size - 1
    start = min(max(1, start), max(1, total))
    end = min(max(start, end), max(1, total))

    try:
        n = int(get("n", default["n"]))
    except ValueError:
        n = default["n"]
    n = min(max(1, n), 300)

    seed = get("seed", default["seed"])
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        seed = random.randint(1, 10 ** 6)

    picked = [t for t in (get("types", "") or "").split(",") if t in types] or types
    graded = str(get("graded", default.get("graded", "0"))) in ("1", "true", "yes")
    return {"level": level, "mode": mode, "type": type_name, "start": start, "end": end,
            "n": n, "seed": seed, "types": picked, "graded": graded, "go": go}


def build_items(r):
    if r["mode"] == "random":
        return items_random(r["level"], r["types"], r["n"], r["seed"], r.get("graded", False))
    if r["mode"] == "exam":
        return items_exam(r["level"], r["seed"], r.get("graded", False))
    return items_batch(r["level"], r["type"], r["start"], r["end"])


class Handler(BaseHTTPRequestHandler):
    conf = {}

    def log_message(self, fmt, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if u.path == "/api/data":
            r = parse_req(qs, self.conf)
            self._send(200, json.dumps(build_items(r), ensure_ascii=False), "application/json")
            return
        if u.path not in ("/", "/index.html"):
            self._send(404, "not found")
            return
        r = parse_req(qs, self.conf)
        if r["mode"] == "home":
            self._send(200, page_home(r["level"]))
        elif r["mode"] == "bank":
            self._send(200, page_bank(r["level"]))
        elif r["mode"] == "exam" and not r.get("go"):
            self._send(200, page_exam_intro(r["level"]))
        else:
            self._send(200, page_html(r, build_items(r)))

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/api/submit":
            self._send(404, "not found")
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        answers = body.get("answers") or {}
        r = parse_req({k: [str(v)] for k, v in body.items() if k != "answers"}, self.conf)
        items = build_items(r)
        res = grade(items, answers)
        save_record(r, items, answers, res)
        self._send(200, json.dumps(res, ensure_ascii=False), "application/json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="3", choices=["3", "4"])
    ap.add_argument("--mode", default="home", choices=["home", "bank", "exam", "batch", "random"],
                    help="home=入口页（默认）；bank=题库目录；exam=模拟卷；batch/random=直接刷题")
    ap.add_argument("--type", default="判断题", help="batch 模式的题型")
    ap.add_argument("--types", default="", help="random 模式的题型，逗号分隔，默认全部")
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--to", dest="end", type=int, default=20)
    ap.add_argument("--n", type=int, default=20, help="random 模式抽题数")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--graded", action="store_true", help="随机/模拟卷只抽有答案的题")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    Handler.conf = {"level": a.level, "mode": a.mode, "type": a.type,
                    "start": a.start, "end": a.end, "n": a.n,
                    "seed": a.seed or random.randint(1, 10 ** 6), "types": a.types,
                    "graded": "1" if a.graded else "0"}
    if a.mode == "exam":
        Handler.conf["go"] = "1"

    srv = None
    for port in range(a.port, a.port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if not srv:
        raise SystemExit("端口 %d 起 20 个都被占用，换 --port" % a.port)

    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("练习页已启动：%s" % url, flush=True)
    if a.mode == "home":
        print("入口页：先选级别（三级/四级），再选「完整题库」或「模拟考题」", flush=True)
    elif a.mode == "bank":
        print("%s级 完整题库目录" % a.level, flush=True)
    elif a.mode == "exam":
        print("%s级 模拟卷（%s）" % (a.level, exam_summary(a.level)), flush=True)
    elif a.mode == "random":
        print("%s级 随机抽题 %d 道（种子 %d）" % (a.level, a.n, Handler.conf["seed"]), flush=True)
    else:
        print("%s级 %s 第%d-%d题" % (a.level, a.type, a.start, a.end), flush=True)
    if not a.no_open:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    srv.serve_forever()


if __name__ == "__main__":
    main()
