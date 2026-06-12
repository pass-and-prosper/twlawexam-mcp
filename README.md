# twexam-mcp

台灣國家考試（考選部）歷屆試題查詢 MCP 伺服器，提供 20 個工具供 Claude Code / Claude Desktop 查題、練習、法條反查、考點分析、弱點複習、考試就緒度評估與考點重點提示。

---

## 安裝

```bash
# 1. 建立虛擬環境
py -m venv .venv

# 2. 安裝套件（可編輯模式）
.venv\Scripts\python -m pip install -e .
```

---

## 在 Claude Code 中使用

Claude Code 會自動讀取專案根目錄的 `.mcp.json`，無需額外設定。
將本專案目錄加入 Claude Code 工作區後，`twexam` 伺服器即自動載入。

---

## 在 Claude Desktop 中使用

編輯 Claude Desktop 的 `claude_desktop_config.json`（位置依平台而定），加入：

```json
{
  "mcpServers": {
    "twexam": {
      "command": "C:\\path\\to\\twexam-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "twexam_mcp.server"]
    }
  }
}
```

> **macOS / Linux 使用者：** 將 `command` 改為 `.venv/bin/python`（POSIX 路徑），例如：
> `"command": "/path/to/twexam-mcp/.venv/bin/python"`

---

## 工具一覽

| 工具名稱 | 用途 |
|---|---|
| `search_questions` | 全文搜尋歷屆考題（匹配題幹、選項、AI 擬答） |
| `get_question` | 以 qid（年-考試-科目-題號）取得單題結構化內容 |
| `list_exams` | 列出可查的考試別與年度範圍 |
| `list_subjects` | 列出科目（可選 exam_code 篩選） |
| `get_exam_paper` | 取整份試卷（某年・某考試・某科目全部題目） |
| `get_answer_key` | 取某份試卷的測驗題標準答案（題號 → 答案） |
| `get_model_answer` | 取申論題 AI 擬答（含免責聲明） |
| `search_by_statute` | 按法條反查考過哪些題目 |
| `get_statute_frequency` | 法條考頻統計（可選 exam_code 篩選） |
| `random_practice` | 依條件隨機抽題練習（支援隱藏答案模式） |
| `get_exam_map` | 考點地圖（科目 → 子科目 → 考點層級，附各科實際題數） |
| `get_topic_distribution` | 考點熱度排行（精準到「抵押權」層級，可選 q_type／exam_code） |
| `practice_by_topic` | 依考點抽題（如「給我抵押權 5 題」，支援隱藏答案模式） |
| `record_answer` | 記錄一次作答（判分 + 更新間隔重複複習排程） |
| `get_progress` | 整體練習進度（已練題數、正確率、待複習數） |
| `get_weak_topics` | 弱點考點排行（正確率最低者優先） |
| `practice_weak` | 針對弱點與待複習考點抽題練習 |
| `reset_progress` | 清空所有作答記錄與複習排程 |
| `get_readiness` | 考試就緒度（依考點頻率加權推估分數、覆蓋率、最拖分考點、每日覆蓋進度） |
| `get_topic_primer` | 考點重點提示（核心法條／常考判決釋字／學說對立／易錯陷阱，做題前必讀） |

---

## 資料來源

本題庫資料來源為考選部公開資訊（政府公開資料），網域範圍：`wwwq.moex.gov.tw`、`wwwc.moex.gov.tw`。

本套件已**內建完整歷屆題庫** `twexam_mcp/data/questions.db`（109–114 年司律一試／二試，共 1940 題），打包進 wheel 後即為自帶資料、安裝即用，毋須執行 ingestion（Playwright／連網）。若 DB 不存在，伺服器會退回 4 題示範種子（`twexam_mcp/data/seed.json`）。

題庫由 **Plan 2 建置流程**（`python -m twexam_mcp.ingest.run`）自考選部公開資料下載、解析後產生；該流程為選用相依（`pip install -e ".[ingest]"`），一般使用者不需安裝。

> **練習記錄存放位置：** 弱點引擎（`record_answer` 等）的作答記錄與複習排程，寫入你本機安裝的 `questions.db`（`attempts` / `review_state` 表）。記錄是**單機、個人**的；**重新安裝或升級 wheel 會覆蓋該 DB、清空練習記錄**。若日後要保留升級前的進度，請先備份 `questions.db`。

### 打包為可散布套件

發佈版請用 `scripts/build_release.py`，它會在打包時**清空個人練習記錄**（`attempts` / `review_state`），
再無條件還原你本機的完整 DB（try/finally 保證你的進度不會遺失）：

```bash
.venv\Scripts\python scripts\build_release.py
# 產生 dist\twexam_mcp-0.5.0-py3-none-any.whl（含完整題庫 DB、但不含你的作答史）
# 安裝後可用 console 指令 twexam-mcp 啟動，或 python -m twexam_mcp.server
```

> 直接 `pip wheel .` 也能打包，但會把你**本機的作答記錄一起**包進 wheel — 要散布給別人請用上面的 build script。

---

## DISCLAIMER 免責聲明

- **`get_model_answer` 所提供之 AI 擬答為機器自動生成，並非官方解答或任何主管機關之見解。**
- 本伺服器之所有內容**不得作為應試依據、法律意見或任何正式文件之引用**。
- 考選部公告之標準答案與評分準則以官方公告為準，本工具不提供保證。
- 使用者應自行判斷資訊之準確性，作者及貢獻者不承擔任何因使用本工具所生之損失或法律責任。

---

## 授權

MIT License — 詳見 [LICENSE](LICENSE)。
