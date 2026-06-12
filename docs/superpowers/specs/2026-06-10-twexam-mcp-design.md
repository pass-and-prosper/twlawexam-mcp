# twexam-mcp 設計規格

- **日期**：2026-06-10
- **狀態**：設計已核可，待寫實作計畫
- **基準**：對標 [lawchat-oss/mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db)，原則「規格只能更高不能更低」

---

## 1. 目標與範圍

建立一個查詢**台灣法律專業考試歷屆試題**的 MCP server，讓任何 MCP AI agent 能搜題、取題、按法條反查、抽題練習。

### 決策（已與使用者確認）
| 項目 | 決定 |
|---|---|
| 考試範圍 | **只做法律專業考試**（律師、司法官＝司律一試/二試、司法特考等法律類科） |
| 資料來源 | **考選部官方 PDF 為正本** + **測驗題官方標準答案**；申論題無官方答案，由**自家 LLM 生成「AI 擬答」**。**不爬第三方聚合網站**（TOS/著作權風險） |
| 使用情境 | 溫書/練題、法條檢索（考頻 trend）、館內知識庫（RAG 語料/few-shot） |
| 第一版垂直切片 | **司律一試 + 二試、近 3 年**，打通「下載→解析→拆題→配答案→MCP 查得到」整條，再橫向擴年度/考試別 |
| 實作路線 | 路線 A：薄垂直切片優先（最早暴露 PDF 解析風險） |

### 非目標（YAGNI）
- 不做高普考/公職等非法律類科。
- 不做查詢時即時生擬答（每次燒 token、重複生 → 違反成本紅線）；擬答一律批次預生、存 DB、永不重生。
- 不爬聚合網站。

---

## 2. 對標矩陣（只升不降）

| # | legal-db 規格 | twexam-mcp 對應 | 升/平 |
|---|---|---|---|
| 技術棧 | Python + FastMCP SDK | 同 | 平 |
| HTTP | httpx + Playwright fallback（過 WAF） | httpx + **Playwright 為主力**（考選部 ASP.NET postback 表單） | 平 |
| 解析 | HTML parser | **PDF parser**（pdfplumber/PyMuPDF）+ **掃描檔 Gemini OCR fallback** | ⬆️ |
| 生成層 | 無 | **申論題 AI 擬答**（批次預生） | ⬆️ |
| MCP 工具數 | 8 | **10** | ⬆️ |
| 儲存 | SQLite(TTL) + 離線 JSON + FTS | SQLite(TTL，僅 live 抓新公告) + **離線 SQLite + FTS5** | ⬆️ |
| 關聯分析 | 引用關係圖譜（regex 抽字號） | **法條↔題目雙向反查 + 考頻 trend 統計** | ⬆️ |
| 自動更新 | timestamp 檢查 + 背景重抓 | 同機制，偵測**考選部新考季公告** | 平 |
| 打包 | PyPI + pipx + 內建 .mcp.json | 同 | 平 |
| 授權 | MIT + 資料免責 | MIT + 考選部政府公開資料免責 | 平 |
| 測試 | eval 文化 | eval + **ingestion golden-file** + **法條標註 coverage audit** | ⬆️ |

---

## 3. MCP 工具清單（10 個）

沿用 legal-db 的 search/get 雙工具範式。

| # | 工具 | 功能 | 服務情境 |
|---|---|---|---|
| 1 | `search_questions` | 關鍵字全文搜題（FTS5，匹配題幹/選項/擬答） | 溫書、知識庫 |
| 2 | `get_question` | 單題結構化：題幹、選項、標準答案、考試·年度·科目·類科、引用法條、AI擬答 | 全部 |
| 3 | `list_exams` | 列可查考試別 × 年度範圍 | 導覽 |
| 4 | `list_subjects` | 列科目 | 導覽 |
| 5 | `get_exam_paper` | 取整份試卷（某年·某考試·某科目全題） | 溫書 |
| 6 | `get_answer_key` | 測驗題官方標準答案 | 溫書、練題 |
| 7 | `get_model_answer` | 申論題 AI 擬答 | 溫書 |
| 8 | `search_by_statute` | 按法條反查考過哪些題（legal-db get_citations 的雙向升級） | 法條檢索 |
| 9 | `get_statute_frequency` | 法條/主題考頻 trend 統計（年度分佈、熱點法條） | 法條檢索 |
| 10 | `random_practice` | 依條件抽題練習 | 練題 |

---

## 4. 架構與目錄結構

照抄 legal-db 骨架，多一層 `ingest/` ETL（legal-db 是 live HTML 解析，本專案需 PDF→結構化離線管線）。

```
twexam_mcp/
├── server.py          # FastMCP 入口（10 個 @mcp.tool()）
├── config.py          # 白名單 domain、考試代碼表、TTL 設定
├── updater.py         # 偵測考選部新考季公告 → 背景重抓
├── cache/
│   └── db.py          # SQLite 層（FTS5）
├── models/            # Question / ExamPaper / ModelAnswer dataclass
├── ingest/            # ← ETL 層（legal-db 無）
│   ├── downloader.py      # 考選部 PDF 抓取（Playwright postback + httpx）
│   ├── pdf_parser.py      # PDF → 拆題（pdfplumber/PyMuPDF + Gemini OCR fallback）
│   ├── answer_matcher.py  # 配測驗題標準答案
│   ├── statute_tagger.py  # 法條抽取/標註（labor tier = Gemini Flash）
│   └── model_answer_gen.py# 申論題擬答批次生成（Batch API −50%）
├── parsers/           # 共用解析 util
├── data/
│   ├── questions.db       # 題庫主存（FTS5）
│   ├── exams_index.json   # 考試別 × 年度可用清單
│   └── statute_xref.json  # 法條 → 題目反查索引
├── tools/
│   ├── question_search.py
│   ├── question_doc.py
│   ├── exam_catalog.py
│   ├── statute_xref.py
│   └── practice.py
└── .mcp.json          # Claude Code 自動註冊
```

### 模組邊界
- `ingest/*`：離線執行，唯一會寫 `data/` 的層。對外介面＝產出結構化 `Question` 物件。
- `cache/db.py`：唯一碰 SQLite 的層；對外＝query 函數。
- `tools/*`：唯一被 `server.py` 的 `@mcp.tool()` 呼叫；對外＝MCP 工具回傳結構。
- `server.py`：只做 wiring，不寫 SQL、不呼叫 LLM。

---

## 5. 資料流（零斷點）

```
考選部(年度 + 考試代碼)
  → downloader.py 抓 PDF
  → pdf_parser.py 拆成 Question{題號, 題型(申論/測驗), 題幹, 選項[], 科目, 類科}
  → answer_matcher.py 以 (年度,考試,科目,題號) 為 key 配標準答案
  → statute_tagger.py 標 引用法條[]
  → cache/db.py 寫入 questions.db(FTS5) + statute_xref.json
  → tools/* 查詢
  → MCP agent
```

**欄位一致性鐵律**：`(year, exam_code, subject, q_no)` 為題目主鍵，從拆題、配答案、寫 DB、反查全程同名同型。測驗題答案配對以此複合鍵 join，配對率須在 ingestion 後驗證（見 §8）。

---

## 6. PDF 解析策略（最大技術風險）

- **Phase 0 spike（先做）**：抓 1 份司律一試 PDF，驗證能否穩定拆題。先驗證下載（postback 表單）＋拆題兩個未知。
- 版型不穩 → 「題號錨點 regex（如 `^一、`/`^1.`）＋ 版面座標」雙策略。
- 申論題（無官方答案）／測驗題（標準答案另檔公告）分流。
- 掃描版 PDF（pdfplumber 回 0 字）→ Gemini Vision OCR（labor tier），抽出文字存 DB 雙保險。

---

## 7. 成本紀律（全域 CLAUDE.md 紅線，寫進設計）

| 工作 | tier | 模型 | 備註 |
|---|---|---|---|
| 法條標註/分類 | labor | Gemini Flash（`gemini-2.5-flash`） | 禁用 Pro/Opus |
| 申論擬答草擬 | mid | Sonnet 4.6 或 Gemini Pro | **走 Batch API −50%，生一次存 DB 永不重生** |
| 掃描 OCR | labor | Gemini Vision | |
| 測試/評分 | $0 | codex/本地 | **禁用 metered API** |

- 靜態前綴（擬答 system prompt、法規語料）放最前面 + prompt cache 攤平。
- 無 storage 計費的隱式/自動快取優先，**禁用 Gemini 顯式 cachedContents**。

---

## 8. 錯誤處理與測試（對齊 eval 文化 + 加碼三層驗證）

- **L1 靜態**（每次 ingestion）：每份試卷拆出題數 vs 預期、測驗題答案配對率、法條標註率；低於閾值報警。
- **L2 結構**（加新考試別/年度後）：法條標註 coverage audit — 遍歷 (科目 × 年度)，列 N=0 的 silent gap。
- **L3 runtime**（抽樣）：真查幾題確認 MCP 回傳對。
- **ingestion golden-file**：固定數份 PDF → 預期拆出的 Question，鎖死回歸。
- **MCP 工具契約測試**：每個 tool 真呼叫一次驗回傳結構。

---

## 9. 打包與授權

- PyPI 套件 `twexam-mcp` + 建議 `pipx install`。
- 內建 `.mcp.json`：`{"mcpServers":{"twexam":{"command":".venv/bin/python","args":["-m","twexam_mcp.server"]}}}`。
- MIT License。
- 免責：考選部試題為政府公開資料；AI 擬答為機器生成、非官方解答、不得作為應試或法律意見依據，使用前須向官方/權威來源驗證。

---

## 10. 開放項（實作計畫處理）

- 考選部 PDF 下載的 postback 表單實際參數（Phase 0 spike 釐清）。
- 各年度試卷版型差異實際幅度（spike 後決定 parser 複雜度）。
- 申論擬答品質驗收標準（誰、用什麼 rubric）。
