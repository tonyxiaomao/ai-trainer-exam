---
name: ai-trainer-exam
display_name: "人工智能训练师（三级/四级）考级题库与模拟考试"
description: "本地网页刷题：首页二级入口先选「完整题库」或「模拟考题」——完整题库按题型顺序刷全部题目（20 题一组，点选即时判分），模拟考题按官方卷构成随机组卷（三级 190 题／四级 200 题，满分 100、90 分钟倒计时、交卷出分）。另含判分讲题、错题本、操作技能试题单与评分表。触发词：人工智能训练师、训练师三级、训练师四级、考级刷题、理论题库、操作技能、模拟试卷、组卷、押题、错题本。"
description_en: "AI trainer (level 3/4) Chinese vocational exam bank: local web page with a two-level entry (full question-bank practice vs. full mock exam), sequential practice in 20-question batches, randomized mock papers matching the official structure (190/200 questions, 100 points, 90-minute timer, instant grading), wrong-answer book, practical-skill task sheets and rubrics, plus Word-to-markdown ingestion."
version: 1.4.0
author: workbuddy
license: MIT
tags:
  - 人工智能训练师
  - 考级题库
  - 模拟考试
  - 刷题
  - 错题本
  - 操作技能
level: personal
metadata:
  data_classification: L1
---

# 人工智能训练师（三级/四级）考级题库与模拟考试

所有命令都在 skill 根目录执行：

```bash
cd ~/.workbuddy/skills/ai-trainer-exam
```

## 一、题库现状（先看这个，再决定怎么答）

| 级别 | 判断题 | 单选题 | 多选题 | 操作技能试题 |
|---|---|---|---|---|
| 三级 | 300（官方答案 40） | 300（140） | 300（10） | 40（评分表 40／参考答案 6） |
| 四级 | 250（50） | 500（150） | — | 31（评分表 30／参考答案 4） |

**答案来源只有官方模拟卷**：两套模拟卷共 390 道理论题（190+200），100% 落在题库内，因此这 390 题的答案权威；其余 1260 题（三级 710、四级 550）在原文档里就没有答案——复习题文件本身就是无答案版，不是我们漏转了。

据此必须遵守：

- 有官方答案的题，判分只信 `practice.py grade` / `mock.py grade`。
- 无官方答案的题，判分脚本会标为「原卷未给答案」。此时你可以凭专业知识判断，但**必须声明「AI 判定，非官方答案」**，并解释依据；用户认可后用 `annotate` 落库，下次即按官方答案对待。
- 绝不把 AI 判断说成官方答案，也不要把题库里空着的答案编一个填进去。
- 不要整篇读取 `data/*.md`（1650 题、约 49 万字符），一律用脚本切片。

随时核对：`python3 scripts/practice.py list`

## 二、命令速查

```bash
# 题库概览
python3 scripts/practice.py list

# 顺序刷题（按原题库题号）
python3 scripts/practice.py show --level 3 --type 判断题 --from 1 --to 20
python3 scripts/practice.py show --level 3 --type 单选题 --from 41 --to 60 --ans   # --ans 带答案（背题模式）

# 随机抽题
python3 scripts/practice.py random --level 4 -n 20 --type 单选题 --seed 7
python3 scripts/practice.py random --level 3 -n 20            # 不指定类型=三种题型混合

# 关键词检索（查某个知识点考过哪些题）
python3 scripts/practice.py search --level 4 -q 数据清洗 --limit 10

# 判分（题号=题库原题号；判断题用 √ / ×，多选写字母串）
python3 scripts/practice.py grade --level 3 --type 判断题 --answers "1:√,2:×,3:√"
python3 scripts/practice.py grade --level 3 --type 多选题 --answers "1:ABC,2:ABCDE"

# 错题本 / 统计
python3 scripts/practice.py wrong
python3 scripts/practice.py wrong --clear
python3 scripts/practice.py stats

# 没有官方答案的题，确认答案后落库（src: ai / user）
python3 scripts/practice.py annotate --level 3 --type 判断题 --n 1 --ans √ --src ai

# 网页练习（点选作答，提交即判分）
./start.sh                                # 首页：选级别 → 完整题库 / 模拟考题
./start.sh 3 题库                         # 三级 完整题库目录（判断题/单选题/多选题）
./start.sh 3 模拟                         # 三级 模拟卷说明页（两种组卷方式）
./start.sh 3 模拟 1                       # 三级 模拟卷，只抽有答案的题（可自动判分）
./start.sh 3 判断题 1 20                  # 跳过首页，直接刷
./start.sh 3 随机 20                      # 三级 跨题型随机 20 题
python3 scripts/web.py --level 3 --mode exam --graded --no-open

# 模拟试卷
python3 scripts/mock.py official --level 3                 # 还原官方理论模拟卷
python3 scripts/mock.py official --level 3 --key           # 带答案
python3 scripts/mock.py gen --level 3                      # 随机组一套理论卷
python3 scripts/mock.py gen --level 4 --kind ops           # 随机组操作技能卷
python3 scripts/mock.py key --paper official-3-theory      # 答案（也可换成生成的试卷号）
python3 scripts/mock.py grade --paper <试卷编号> --answers "1:√,2:×,3:A"
python3 scripts/mock.py papers                             # 已生成的试卷
```

## 三、网页练习（用户说“在页面里做/方便填写/来点随机题”时首选）

`start.sh` + `scripts/web.py`：纯标准库的本地小服务，只监听 `127.0.0.1`。

**两级入口**（用户说“没有题库刷题模式”就是缺这个）：

1. 首页 `/`：选级别（三级 / 四级，右上角切换），然后二选一
2. 二级选择：
   - **完整题库**（`mode=bank`）→ 题型目录（判断 / 单选 / 多选，显示题量与可判题数）→ **batch** 分组刷（默认 20 题一组，可翻上一组/下一组，有「继续上次」直跳上次停下的题号）
   - **模拟考题**（`mode=exam`）→ 试卷说明页（卷面构成表 + 两种组卷方式）→ 整卷作答页

模拟卷两种组卷方式：

| 方式 | 取题 | 判分 |
|---|---|---|
| 全库随机 | 整个题库抽，覆盖面最大 | 约 1/4 题可机判，其余标「需 AI 判定」，交卷后给「按可判题折算 xx/100」 |
| 只用有答案的题 | 只抽有答案的题（三级 55/140/10，四级 50/150） | 整卷 100% 可机判，直接出真实分数 |

模拟卷页面：题号全卷连续（1…190 / 1…200），按官方顺序分节（一、判断题 → 二、单选题 → 三、多选题），顶部 90 分钟倒计时（最后 5 分钟变红，到点自动交卷），分节锚点可跳转，交卷前会提示未作答题数。

页面能力：判断题点 √/×，选择题点字母（多选可多选），键盘 `1`/`2`、`A`~`E` 也能答，答完自动滚到下一题；提交即时显示对错、正确答案、答案来源徽标与讲解备注；`复制作答` 出 `1:√,2:×` 串；作答落 `records/`。

**自助运行（用户自己在本地起）**

```bash
cd ~/.workbuddy/skills/ai-trainer-exam
./start.sh                    # 首页：选级别 → 完整题库 / 模拟考题（自动开浏览器）
./start.sh 3 题库             # 三级 完整题库目录
./start.sh 3 模拟             # 三级 模拟卷说明页
./start.sh 3 判断题 1 20      # 直接刷某一区间，跳过首页
./start.sh 3 随机 20          # 三级 跨题型随机 20 题（全库）
PORT=8800 ./start.sh          # 指定端口；被占用自动顺延
```

- 依赖只有 Python 3（macOS/Linux 自带，Windows 用 python.org 版），**不联网、不装包、数据不出本机**。
- 停止：终端 `Ctrl+C`。命令行等价：`python3 scripts/web.py --level 3 --mode home`。
- Windows 把 `./start.sh` 换成 `python scripts\web.py --level 3 --mode home`。

**Agent 侧要点**

- 起服务后**用 `present_files` 传 `http://127.0.0.1:<port>/`**，别把 20 道题贴进对话；用户要刷题就给首页，让他自己选完整题库还是模拟考。
- 判分优先级：`records/corrections.json`（已确认）> 题库官方答案 > `records/ai-judgments.json`（AI 判定，页面标「AI 判定·非官方」）。三者都无的题显示「待判定」，提交后读 `records/submissions/latest.json` 的 `pending`，在对话里逐题判定。
- 补 AI 判定层：`records/ai-judgments.json` 写 `{"3:判断题:18": {"ans":"√","note":"依据","src":"ai"}}`，页面立刻能判；用户认可后 `practice.py annotate` 转正。没把握的题别写进去。
- URL 参数：`?mode=bank&level=3`、`?mode=exam&level=3`（说明页）、`?mode=exam&level=3&go=1&graded=1&seed=42`（整卷，`seed` 相同可复现）、`?mode=random&level=3&n=20&graded=1&seed=42`、`?mode=batch&level=3&type=单选题&from=41&to=60`。
- 批次大小默认 20；服务是前台进程，用后台任务启动，会话结束可能被回收，下次要做重新起。

## 四、组卷规则（与官方卷一致，来自卷首抬头）

| 级别 | 题型构成 | 配分 | 时间 |
|---|---|---|---|
| 三级 | 判断 40 + 单选 140 + 多选 10 | 0.5／0.5／1，共 100 分 | 90min |
| 四级 | 判断 50 + 单选 150 | 0.5／0.5，共 100 分 | 90min |
| 三级技能 | 6 题：1.1.1(25) 2.1.1(15) 2.2.1(20) 3.1.1(15) 3.2.1(20) 4.2.1(5) | 100 分 | 120min |
| 四级技能 | 5 题：1.1.1(20) 1.2.1(10) 2.1.1(30) 2.2.1(20) 3.2.5(20) | 100 分 | 120min |

`gen` 严格按上表题量/配分/时间组卷，题号全卷连续编号（1…190 / 1…200），便于一次性作答与判分。两种取题模式：

- `--mode mixed`（默认）：从整个题库随机抽，覆盖面最大；因题库里只有 390 题有官方答案，一套卷里能机判的约 60～75 题，其余需你在交卷后按知识判断（脚本会列出题号）。
- `--mode graded`：只取有官方答案的题，整卷可机判，但题量刚好等于官方卷，等于固定那 190/200 题，随机性很弱（判断+单选不够时会告警）。

组卷后脚本会打印「本卷 N 题中 M 题可机判」——把这句话转述给用户，别让他以为剩下的是漏题。

操作技能随机卷沿用官方各题配分与时间（合计 100 分），抽到的试题本身可能与配分不完全对应，讲题时以评分表的采分点为准。

## 五、典型工作流

**1）全题库刷题（用户说“我要刷三级理论题”）**
`list` 报家底 → 按 20 题一组 `show --from --to` 出题（不带答案）→ 用户作答 → `grade` 判分 → 只讲错题：为什么错、正确选项依据、易混点。用户没喊停就继续下一组；下次接续的题号问一下用户，或从 `stats` 看已刷到哪。

**2）模拟考试（用户说“来一套模拟卷”）**
默认 `mock.py gen --level N`（随机卷）或 `official`（原版卷）→ 只贴试卷，不给答案 → 用户交卷 → `mock.py grade --paper <id> --answers "..."` → 报分（分题型 + 总分）→ 逐题讲错。
操作技能卷不能自动判分：`mock.py key --paper <id>` 输出评分表 + 参考答案，引导用户按评分点自评，可用 `practice.py annotate` 记录薄弱模块。

**3）错题复习**
`wrong` 列表 → 按 `level:type:n` 定位原题讲解 → 该题重做对了用 `wrong --rm 3:判断题:12` 移出，全掌握后 `wrong --clear`。

**4）操作技能专项**
`python3 scripts/practice.py list` 拿试题清单；需要完整试题单/评分表：
`python3 scripts/mock.py official --level 3 --kind ops --key`（含评分表与参考答案）。
讲解时按「场地设备要求 → 工作任务拆解 → 评分表采分点 → 参考答案代码」四段走，采分点是拿分关键。

## 六、文件结构

```
data/bank-3.md bank-4.md        理论题库（每行一题：题号|答案|题干|A:选项…，答案空=原卷无答案）
data/ops-3.md  ops-4.md         操作技能（试题单 + 评分表 M1|分|细则 + 参考答案）
data/composition.json           组卷规则（从官方卷抬头解析）
data/manifest.json              来源文件、题量、答案覆盖、官方卷题目清单、体积对比
data/原文档体积 2.46MB → md 487KB（压缩 ~80%，去掉空白与重复试题，模拟卷只存题号）
records/papers/<id>.json|.md    已生成的试卷
records/wrongbook.json          错题本
records/history.json            练习流水
records/corrections.json        已确认的答案（优先级最高，用户 annotate 写入）
records/ai-judgments.json       未确认的 AI 判定（仅供网页即时判分，带“AI 判定”徽标）
records/submissions/latest.json 网页最近一次提交的作答与判分（含 pending 题号）
start.sh                        一键起网页练习：./start.sh [级别] [题库|模拟|题型|随机] [起/题数] [止]
scripts/web.py                  网页服务：home 入口页 / bank 题库目录 / exam 模拟卷 / batch 分组刷 / random 随机抽
```

## 七、维护

- 改了题库：`python3 scripts/build.py rebuild`（会重算 composition.json 与 manifest.json）。
- 想看体积/来源对比：`python3 -c "import json;print(json.load(open('data/manifest.json'))['size'])"`。
- 脚本无第三方依赖，仅 `python-docx`（读 docx）；md 解析、渲染、判分都是标准库。
