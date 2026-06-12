# Phase 0 Spike Findings — 考選部考畢試題下載與解析

- **日期**：2026-06-10
- **方法**：真連 `wwwq.moex.gov.tw`、真下載 PDF、PyMuPDF 真抽文字（非推論）
- **結論**：全部可行，風險解除。本文件是 Plan 2 ingestion 的事實依據。

## 1. 下載機制（確定性，免 cookie）

檔案端點是單一 ashx，GET 即得 PDF，**不需 session cookie**：

```
https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=<TYPE>&code=<EXAM>&c=<CAT>&s=<SUBJ>&q=<SEG>
```

| 參數 | 意義 | 範例 |
|---|---|---|
| `t` | 檔案類型 | `Q`=試題、`S`=申論參考/解析、`A`=全考試測驗題標準答案清冊 |
| `code` | 考試代碼 | `113110`（民國113司律一試）、`113111`（二試） |
| `c` | 類科代碼 | `301` |
| `s` | 科目代碼 | `0101`,`0102`,`0201`,`0202`… |
| `q` | 節次 | `1` |

- `t=A&code=<EXAM>`（不帶 c/s）→ 整份「測驗式試題標準答案清冊」PDF。
- **二試 `t=A` 回傳的是 HTML（非 PDF）** → 二試全為申論題、**無官方標準答案** → 需自建 AI 擬答。
- 需帶 `Referer: https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx` 與一般 UA。

## 2. 科目碼發現（需 Playwright）

搜尋頁 `wFrmExamQandASearch.aspx` 是 ASP.NET WebForms + **UpdatePanel(AJAX) cascading dropdown**：
- 年度下拉 AutoPostBack（`__EVENTTARGET`=下拉），純 httpx 同步 postback 會被伺服器回錯誤頁（「目前無法顯示這個頁面」）→ **discovery 必須用 Playwright**（驅動真瀏覽器處理 AJAX）。
- 流程：選 `#...wUctlExamYearStart$ddlExamYear`（西元年 value，如 `2024`）+ End 年 → 等 2.5s AJAX → 選 `#...ddlExamCode` → click `#...btnSearch` → 結果頁列出每科目的「試題/答案」連結（即上面的 ashx URL，內含 c/s）。
- 結果頁可直接 scrape 出所有 `t=Q`/`t=S` 連結 + 科目名稱。

**分工**：Playwright 只做「列出某考試有哪些 c/s 科目碼 + 科目名」；檔案下載用 httpx 直打 ashx。

## 3. 考試代碼規律

- 格式：`{民國年三碼}{序號三碼}`。司律：`{年}110`=第一試、`{年}111`=第二試。
  - 例：113110/113111（民國113=2024）。實作時仍須用 Playwright 列舉驗證（不同年序號或有例外）。

## 4. PDF 版型（PyMuPDF 可抽，文字型非掃描）

### 4a. 一試（sl1）= 測驗題
`113110` 綜合法學，10 頁、~13k 字。每題結構：
```
<阿拉伯數字題號，獨立一行>
<題幹（可跨行）>
<選項1>           ← 4 個選項，無 A/B/C/D 前綴，靠「題號間 4 段」定位，選項可跨行
<選項2>
<選項3>
<選項4>
```
雜訊行需過濾：`代號：2301`、`頁次：10－2`、卷首 `類科/科目/考試時間/座號/※注意…`。
科目共題數寫在卷首（如「本科目共75題」）。

### 4b. 二試（sl2）= 申論題
`113111` 憲法與行政法，9 頁、~9k 字。每題以**中文序號**起：
```
一、<長案例事實／問題，數十行>
二、…
```
無選項、無官方答案 → 需 AI 擬答。雜訊同上（`代號：30110|30910`、`頁次：9－1`、卷首注意事項）。

## 5. 答案表（一試 t=A）解析陷阱

每科目一塊：`等級名稱 / 類科名稱 / 科目名稱 / <科目代碼 e.g. 2301> / 每題配分 / 題數`，接著：
```
題號  01-10 11-20 21-30 31-40 41-50 51-60
答案  AADBCCADBA
      ACBCCCDCAB
      …（每行 10 字）
71-80 61-70 81-90 91-100    ← 注意：文字抽取後段「題號區段」順序會錯亂（71-80 跑到 61-70 前）
      AABCA
      CBCCDDBABC
```
- **陷阱**：多欄表格被 PyMuPDF 線性抽取後，後段題號區段順序錯亂 → **answer parser 必須用座標感知**（`page.get_text("words")` 取 x/y 重排），不可單純照行序拼。
- 科目代碼（如 `2301`）＝題目 PDF 卷首「代號」，是題目↔答案的 join key。
- 一試同一份答案清冊會出現 3 次（類科：司法官 / 律師 / 司法官及律師）→ 取一份即可，需去重。

## 6. 對 Plan 2 的設計指引

1. `downloader.py`：Playwright 列 c/s（discovery）+ httpx 下載 ashx（檔案）。快取已下載 PDF（離線、檔案不會變）。
2. `pdf_parser.py`：兩個 parser — `parse_mcq_paper`（數字題號錨點 + 4 位置選項）、`parse_essay_paper`（中文序號錨點）。共用 header/footer 雜訊過濾。文字 0 字 → Gemini OCR fallback（罕見）。
3. `answer_matcher.py`：座標感知解析 `t=A` 表 → `{科目代碼: [答案序列]}`；用代號 join 回 MCQ 題；去重類科。
4. `statute_tagger.py`：對題幹抽法條（labor=Gemini Flash）。
5. `model_answer_gen.py`：只對 sl2 申論題，Batch API 生擬答、生一次存 DB。
6. 主鍵沿用 Plan 1 schema：`qid=年-exam_code-subject-q_no`（exam_code=sl1/sl2，年用民國年）。
