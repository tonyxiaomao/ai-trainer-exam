# 人工智能训练师（三级/四级）考级题库与模拟考试

> 一套纯 Python 标准库实现的**本地刷题 + 模拟考试**工具：题库来自人工智能训练师职业技能等级认定复习资料，做题全在浏览器里点选，提交即判分，数据不出本机。

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](#环境要求)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

## 这是什么

把官方复习资料（Word 题库 + 模拟试卷）转成结构化 Markdown，再包一层本地网页，做成能真正用起来的刷题器：

- **两级入口**：首页先选级别（三级/四级），再选「完整题库」或「模拟考题」——不是一上来就塞一堆题给你
- **完整题库**：按题型顺序刷全部题目，20 题一组，可翻上一组 / 下一组，支持「继续上次」
- **模拟考题**：按官方卷面构成随机组卷（三级 190 题 / 四级 200 题），满分 100、90 分钟倒计时、到点自动交卷
- **点选即答**：判断题点 √/×，选择题点字母，键盘 `1`/`2`、`A`~`E` 也能答，答完自动滚到下一题
- **即时判分**：提交后显示对错、正确答案、答案来源徽标与讲解备注
- **错题本 / 练习流水**：答错自动进错题本，掌握后手动移出
- **操作技能**：三级 40 题、四级 31 题的试题单 + 评分表 + 参考答案，按采分点自评

## 题库现状

| 级别 | 判断题 | 单选题 | 多选题 | 操作技能试题 |
|---|---|---|---|---|
| 三级 | 300（官方答案 40） | 300（140） | 300（10） | 40（评分表 40 / 参考答案 6） |
| 四级 | 250（50） | 500（150） | — | 31（评分表 30 / 参考答案 4） |

**答案来源说明（重要）**：答案只来自官方模拟卷——两套模拟卷共 390 道理论题（三级 190 + 四级 200），100% 落在题库内，这些答案权威。其余 1260 题在原复习资料里**本身就没有答案**（复习题文件即无答案版），不是转换时漏掉的。

因此本项目对答案做了三层分级，页面会用徽标标明来源：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | `records/corrections.json` | 用户确认过的答案，最高优先级 |
| 2 | 题库官方答案 | 来自官方模拟卷，权威 |
| 3 | `records/ai-judgments.json` | **AI 判定，非官方答案**，页面标注「AI 判定」徽标 |
| — | 都没有 | 显示「待判定」，交卷后由 AI 逐题给出结论 |

> 绝不把 AI 判断伪装成官方答案，也绝不给没答案的题凭空编一个答案填进去。

## 快速开始

```bash
git clone https://github.com/tonyxiaomao/ai-trainer-exam.git
cd ai-trainer-exam

./start.sh                 # 打开首页：选级别 → 完整题库 / 模拟考题
```

浏览器会自动打开 `http://127.0.0.1:8765/`。停止用 `Ctrl+C`。

Windows（无 bash）：

```bat
python scripts\web.py --level 3 --mode home
```

### 环境要求

- **Python 3.8+**（macOS / Linux 自带；Windows 到 [python.org](https://www.python.org/downloads/) 装）
- **零第三方依赖**：网页服务、MD 解析、判分、组卷全部用标准库；只有需要从 `.docx` 重新导入题库时才用 `python-docx`
- **不联网**，服务只监听 `127.0.0.1`，答题记录全部落在本地 `records/`

### 启动参数

```bash
./start.sh                    # 首页（选级别 → 完整题库 / 模拟考题）
./start.sh 3                  # 直接进三级首页
./start.sh 3 题库              # 三级 完整题库目录（判断/单选/多选）
./start.sh 3 模拟              # 三级 模拟卷说明页（两种组卷方式）
./start.sh 3 模拟 1            # 三级 模拟卷，只抽有答案的题（100% 可机判）
./start.sh 3 判断题 1 20       # 跳过首页，直接刷第 1-20 题
./start.sh 3 随机 20           # 三级 跨题型随机 20 题
PORT=8800 ./start.sh          # 指定端口（被占用自动顺延）
```

### URL 参数

| 参数 | 示例 |
|---|---|
| 题库目录 | `?mode=bank&level=3` |
| 模拟卷说明页 | `?mode=exam&level=3` |
| 整卷作答 | `?mode=exam&level=3&go=1&graded=1&seed=42` |
| 随机抽题 | `?mode=random&level=3&n=20&graded=1&seed=42` |
| 分组刷题 | `?mode=batch&level=3&type=单选题&from=41&to=60` |

`seed` 相同时抽到的题完全一致，方便复现同一套卷。

## 模拟卷规则

严格按官方卷首抬头还原：

| 级别 | 题型构成 | 配分 | 时间 |
|---|---|---|---|
| 三级理论 | 判断 40 + 单选 140 + 多选 10 | 0.5 / 0.5 / 1，共 100 分 | 90 min |
| 四级理论 | 判断 50 + 单选 150 | 0.5 / 0.5，共 100 分 | 90 min |
| 三级技能 | 6 题：1.1.1(25) 2.1.1(15) 2.2.1(20) 3.1.1(15) 3.2.1(20) 4.2.1(5) | 100 分 | 120 min |
| 四级技能 | 5 题：1.1.1(20) 1.2.1(10) 2.1.1(30) 2.2.1(20) 3.2.5(20) | 100 分 | 120 min |

两种组卷方式：

| 方式 | 取题范围 | 判分效果 |
|---|---|---|
| 全库随机 | 整个题库抽，覆盖面最大 | 约 1/4 可机判，其余标「需 AI 判定」，交卷后按可判题折算 |
| 只用有答案的题 | 只抽有答案的题（三级 55/140/10，四级 50/150） | 整卷 100% 可机判，直接出真实分数 |

题号全卷连续编号（1…190 / 1…200），按官方顺序分节，顶部倒计时最后 5 分钟变红，交卷前提示未作答题数。

## 命令行用法

网页是主要入口，命令行适合脚本化整理和批量判分：

```bash
# 题库概览
python3 scripts/practice.py list

# 顺序刷题 / 背题模式（--ans 带答案）
python3 scripts/practice.py show --level 3 --type 判断题 --from 1 --to 20
python3 scripts/practice.py show --level 3 --type 单选题 --from 41 --to 60 --ans

# 随机抽题
python3 scripts/practice.py random --level 4 -n 20 --type 单选题 --seed 7

# 关键词检索（查某个知识点考过哪些题）
python3 scripts/practice.py search --level 4 -q 数据清洗 --limit 10

# 判分（题号=题库原题号；判断题用 √/×，多选写字母串）
python3 scripts/practice.py grade --level 3 --type 判断题 --answers "1:√,2:×,3:√"
python3 scripts/practice.py grade --level 3 --type 多选题 --answers "1:ABC,2:ABCDE"

# 错题本 / 统计
python3 scripts/practice.py wrong
python3 scripts/practice.py stats

# 组卷
python3 scripts/mock.py official --level 3          # 还原官方理论卷
python3 scripts/mock.py official --level 3 --key    # 带答案
python3 scripts/mock.py gen --level 3               # 随机组一套理论卷
python3 scripts/mock.py gen --level 4 --kind ops    # 随机组操作技能卷
python3 scripts/mock.py key --paper official-3-theory
python3 scripts/mock.py grade --paper <试卷编号> --answers "1:√,2:×,3:A"
python3 scripts/mock.py papers                      # 已生成的试卷
```

## 目录结构

```
├── start.sh                    一键起网页练习（首页/题库/模拟/题型/随机）
├── SKILL.md                    Agent 侧使用说明（工作流、判分优先级、注意事项）
├── data/
│   ├── bank-3.md  bank-4.md    理论题库：每行一题 `题号|答案|题干|A:选项…`，答案空=原卷无答案
│   ├── ops-3.md   ops-4.md     操作技能：试题单 + 评分表 + 参考答案
│   ├── composition.json        组卷规则（从官方卷抬头解析）
│   └── manifest.json           来源文件、题量、答案覆盖、官方卷题目清单
├── records/
│   ├── papers/                 已生成的试卷（json + md）
│   ├── wrongbook.json          错题本
│   ├── history.json            练习流水
│   ├── corrections.json        用户确认的答案（优先级最高）
│   ├── ai-judgments.json       AI 判定（未确认，仅供即时判分）
│   └── submissions/latest.json 网页最近一次提交的作答与判分
└── scripts/
    ├── lib.py                  题库加载 / 切片 / 判分公共逻辑
    ├── practice.py             命令行刷题、判分、错题本
    ├── mock.py                 官方卷还原与随机组卷、判分
    ├── web.py                  网页服务（home / bank / exam / batch / random）
    └── build.py                docx → markdown 重建与统计
```

原始 Word 资料共 2.46 MB，转成 Markdown 后约 487 KB（压缩约 80%）：去掉重复题干与空白，模拟卷只存题号。

## 维护

```bash
python3 scripts/build.py rebuild   # 改了题库后重建 composition.json / manifest.json
```

数据格式极简，改题直接编辑 `data/bank-3.md`：`题号|答案|题干|A:选项|B:选项…`，答案留空表示原卷未给答案。

## 免责声明

题库与评分表整理自人工智能训练师职业技能等级认定公开复习资料，**仅供个人学习复习使用**，版权归原作者/出版方所有。模拟卷为按官方卷面结构随机组卷，不等同于真题，考试内容与配分请以官方发布为准。

## License

[MIT](./LICENSE)
