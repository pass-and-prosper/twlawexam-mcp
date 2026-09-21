# twlawexam-mcp

[![PyPI](https://img.shields.io/pypi/v/twlawexam-mcp)](https://pypi.org/project/twlawexam-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/twlawexam-mcp)](https://pypi.org/project/twlawexam-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/pass-and-prosper/twlawexam-mcp/blob/main/LICENSE)

台灣**司法官／律師考試**（司律一試、二試）歷屆試題 MCP 伺服器。
內建 109–114 年共 **1,940 題**（含測驗題標準答案、申論題 AI 擬答、法條反查、考點與爭點索引），
裝好就能在 Claude Code / Claude Desktop 裡查題、抽題練習、記錄作答、看弱點、排讀書計畫、讓 AI 逐爭點批改申論。

資料留在你本機，不上雲、不連網、不需要 API key。

---

## 安裝（一行）

需要 [uv](https://docs.astral.sh/uv/)（沒有的話：`pip install uv`）。

**Claude Code**

```bash
claude mcp add twlawexam -- uvx twlawexam-mcp
```

**Claude Desktop** — 在 `claude_desktop_config.json` 加入：

```json
{
  "mcpServers": {
    "twlawexam": {
      "command": "uvx",
      "args": ["twlawexam-mcp"]
    }
  }
}
```

**其他 MCP 客戶端**（Cursor、Codex、Cline…）：指令都是 `uvx twlawexam-mcp`，stdio 傳輸。

裝好之後對 Claude 說「給我抵押權 5 題」「我常錯什麼」「剩 30 天怎麼念」就會動了。
伺服器自帶教學指令（怎麼出題、怎麼批改申論、怎麼安排複習），不用自己寫 prompt。

> 還沒上 PyPI 之前，或想用 GitHub 最新版：
> `uvx --from git+https://github.com/pass-and-prosper/twlawexam-mcp twlawexam-mcp`

---

## 能做什麼

### 查題
| 工具 | 用途 |
|---|---|
| `search_questions` | 全文搜尋歷屆考題（匹配題幹／選項／擬答） |
| `get_question` | 以 qid（年-考試-科目-題號）取得單題結構化內容 |
| `list_exams` / `list_subjects` | 列出可查的考試別、年度範圍與科目 |
| `get_exam_paper` | 取整份試卷（某年・某考試・某科目全部題目） |
| `get_answer_key` | 測驗題標準答案（題號 → 答案） |
| `get_model_answer` | 申論題 AI 擬答（含免責聲明） |
| `search_by_statute` | 按法條反查考過哪些題 |
| `get_statute_frequency` | 法條考頻統計 |

### 考點與爭點
| 工具 | 用途 |
|---|---|
| `get_exam_map` | 考點地圖：科目 → 子科目 → 考點層級，附各科實際題數 |
| `get_topic_distribution` | 考點熱度排行（精準到「抵押權」層級） |
| `get_topic_primer` | 考點重點提示：核心法條／常考判決釋字／學說對立／易錯陷阱 |
| `get_issue_distribution` | 申論爭點熱度排行（學說／實務交鋒點） |
| `search_by_issue` | 依爭點找題，附各題的學說對立與實務見解 |
| `get_issues` | 取某申論題拆出的所有爭點與實務字號 |
| `get_issue_primer` | 爭點重點包：辨識訊號、前置觀念、考點重點 |
| `get_issue_chain` | 爭點脈絡圖：一題多個爭點的先決問題鏈 |

### 練習與批改
| 工具 | 用途 |
|---|---|
| `random_practice` | 依條件隨機抽題（可隱藏答案） |
| `practice_by_topic` | 依考點抽題（「給我抵押權 5 題」） |
| `essay_exam_by_topic` | 考點申論題卷（模擬考） |
| `record_answer` | 記錄作答、自動批改、更新間隔重複排程 |
| `get_grading_rubric` | 申論批改評分表：爭點 checklist、學說對立、實務字號、五維評分準則 |

### 進度、弱點、讀書計畫
| 工具 | 用途 |
|---|---|
| `get_progress` | 學習總覽：作答數、答對率、今天到期複習數 |
| `get_weak_topics` | 弱點地圖：各考點答對率由弱到強 |
| `practice_weak` | 弱點練習：優先出到期複習與最弱考點 |
| `get_error_diagnosis` | 錯誤類型診斷：觀念混淆／掉陷阱／粗心 |
| `get_readiness` | 考試就緒度：依考點頻率加權推估分數與覆蓋率 |
| `get_study_plan` | 讀書計畫：綁考試日，排出攻擊順序與今日任務 |
| `reset_progress` | 清空作答記錄與複習排程 |

---

## 練習記錄放哪裡

作答記錄與複習排程寫在你本機的 `progress.db`，與題庫分開存放，是單機、個人的資料，不會被打包或上傳。
自 0.6 起它放在使用者資料夾、不在套件目錄裡，所以升級套件不會清掉進度：

| 平台 | 位置 |
|---|---|
| Windows | `%LOCALAPPDATA%\twlawexam-mcp\progress.db` |
| macOS | `~/Library/Application Support/twlawexam-mcp/progress.db` |
| Linux | `$XDG_DATA_HOME/twlawexam-mcp/progress.db`（預設 `~/.local/share/...`） |

要換位置（例如放進雲端同步資料夾），設環境變數 `TWEXAM_PROGRESS_DB` 指到檔案路徑即可。

---

## 手機也能用

把伺服器改成 HTTP 模式，配 Cloudflare Tunnel 接到 Claude.ai 的自訂連接器，手機 App 就能用同一份題庫。
步驟見 [docs/phone-setup.md](https://github.com/pass-and-prosper/twlawexam-mcp/blob/main/docs/phone-setup.md)。

---

## 從原始碼開發

```bash
git clone https://github.com/pass-and-prosper/twlawexam-mcp
cd twlawexam-mcp
uv venv
uv pip install -e ".[dev]"
uv run pytest -q
```

Claude Code 會自動讀專案根目錄的 `.mcp.json`，開發中的版本即載入為 `twexam` 伺服器。
該檔預設指向 Windows 的 `.venv\Scripts\python.exe`，macOS / Linux 請改成 `.venv/bin/python`。

**打包發佈**：`python scripts/build_release.py`。它會先確認題庫裡沒有個人作答資料才打包。

**重建題庫**（一般使用者不需要）：`pip install -e ".[ingest]"` 後執行 `python -m twexam_mcp.ingest.run`，從考選部公開資料重新下載、解析。

---

## 資料來源

考選部公開資訊（政府公開資料），網域：`wwwq.moex.gov.tw`、`wwwc.moex.gov.tw`。

---

## 免責聲明

- `get_model_answer` 與批改素材中的 AI 擬答為機器自動生成，**並非官方解答或任何主管機關之見解**。
- 本工具所有內容不得作為應試依據、法律意見或任何正式文件之引用。
- 考選部公告之標準答案與評分準則以官方公告為準。
- 使用者應自行判斷資訊之準確性，作者及貢獻者不承擔任何因使用本工具所生之損失或法律責任。

---

## 授權

MIT License — 詳見 [LICENSE](https://github.com/pass-and-prosper/twlawexam-mcp/blob/main/LICENSE)。
