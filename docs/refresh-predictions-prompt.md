月度刷新 twexam 的「還沒考過的重要爭點」預測（5 來源）。本機 repo：專案根目錄（已是 cwd）。你是吃到飽訂閱，可用 subagent 平行研究，$0。

目標：重跑下列 5 來源，找「重要但司律二試還沒考過」的爭點，整併進 twexam_mcp/data/untested_issues.json，重生 topic-atlas.html，最後本機 commit（**不要 push**；推由使用者手動，pre-push hook 把關）。

來源（重點抓「自上次以來的新東西」；_pending_refresh.md 有本月偵測到的新憲判字/新考季）：
1. 研究推測：各科重要但未考的爭點（source=研究推測）
2. 高普考領先：近年高普考/司法特考考過、司律未考（source=高普考領先, gk_source）
3. 法律系/PTT 期中期末考：台大等法律系期中末考、PTT/Dcard/補習班熱（source=法律系考古題, ls_source）— **每月必爬，新學期期中期末考會更新**
4. 期刊論文：近 5 年法學期刊（月旦法學/裁判時報/台大法學論叢/政大法學評論…）熱議（source=期刊論文, journal_source）

做法（沿用既有 pipeline）：
- 8 個二試科目各派 subagent；每科讀 W:/tmp/twpred/tested_NN.json 的 tested_issues（已考爭點，避免重複），用 WebSearch/WebFetch + taiwan-legal-db MCP 研究。
- **字號鐵律**：每個釋字/憲判字/最高法院/大法庭字號都要用 taiwan-legal-db 查證存在，查不到的一律丟掉，寧可空、不可掰。學者歸屬只在公認時掛名。
- 每個爭點輸出 {issue, doctrines[], practice[verified], why, source, 對應的 gk_source/ls_source/journal_source}。
- 用 Python 把新結果**併進**現有 untested_issues.json（去重：issue 文字高度相同就合併、保留較多來源標註），再驗一次釋字/憲判字 0 幻覺。
- 跑 `scripts\render_atlas.py topic-atlas.html` 重生。
- `git add twexam_mcp/data/untested_issues.json scripts/`（明確指定檔），commit「data: 月度刷新預測（+N 爭點：來源/新材料摘要）」。**不加 Co-Authored-By、不 push。**

完成後回報：本月新增幾個爭點、來自哪些新材料（新憲判字/新期中期末考/新期刊）。
