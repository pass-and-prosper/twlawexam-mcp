# 手機連線設定（家用 PC + Cloudflare Tunnel）

讓手機 Claude App 用到電腦上的 twexam 題庫。資料留在你電腦（`local` 的 DB 不搬家），免費。
**代價**：電腦要開著、通道要跑著，手機才連得到。

前提：**Claude 付費方案（Pro 或 Max）** 才有「自訂連接器」。沒有就只能桌機用。

---

## 一次性安裝（只做一次）

1. 安裝 cloudflared（系統管理員 PowerShell）：
   ```powershell
   winget install --id Cloudflare.cloudflared
   ```
   （或到 Cloudflare 官網下載 `cloudflared-windows-amd64.exe`，放進 PATH。）

---

## 每次要用（兩個視窗）

### 視窗 1：啟動題庫伺服器
```powershell
powershell -File twexam-mcp\scripts\serve_phone.ps1
```
它會印出你的**連線密碼**（第一次自動產生、之後固定），並在 `127.0.0.1:8000` 開伺服器。
把那串密碼記下來（手機設定要用）。

### 視窗 2：開通道
```powershell
cloudflared tunnel --url http://127.0.0.1:8000 --http-host-header 127.0.0.1:8000
```
它會印出一個網址，像 `https://random-words-1234.trycloudflare.com`。**這就是你的對外網址。**

> ⚠️ `--http-host-header 127.0.0.1:8000` 一定要加。MCP 伺服器有 DNS 重綁定防護，會擋掉非本機的 Host；少了這個參數，帶密碼的請求會回 **421 Invalid Host header**。這個參數讓通道把 Host 改寫成 `127.0.0.1:8000`，伺服器才收。

---

## 在 Claude.ai 加自訂連接器（手機或網頁都可設，設一次手機就有）

1. Claude.ai → Settings → **Connectors** → **Add custom connector**。
2. **URL**：填 `https://你的網址.trycloudflare.com/mcp`（**記得結尾 `/mcp`**）。
3. **驗證**：把密碼當 Bearer token 送 — 在連接器的 header 設定加：
   `Authorization: Bearer 你的密碼`
   > ⚠️ 如果 Claude 當下的連接器介面**只給 OAuth、不給自訂 header**，先別卡住 —
   > 回來告訴我，我把伺服器改成 OAuth 模式（mcp SDK 有支援，只是設定多幾步）。
4. 存檔後，手機 Claude App 對話裡就會出現 **twexam** 的工具（練題、弱點地圖、就緒度、重點提示都能用）。

---

## 注意事項

- **quick tunnel 網址每次重啟會變**。要永久固定網址 → 設 named tunnel（需 Cloudflare 免費帳號 + 一個網域）。要的話跟我說，我給你 named tunnel 的設定。
- **電腦關機 / 通道關掉 → 手機連不到**（這是「資料留在自己電腦」的取捨）。想永遠在線就得改用雲端 VM。
- 密碼存在 `twexam-mcp\.twexam_token`（已 gitignore，不會進版控）。密碼外洩就刪掉這檔、重跑 `serve_phone.ps1` 產新的。
- 安全性：伺服器對外只開一條，且**沒帶對密碼一律 401**；但 quick tunnel 網址是公開可達的，所以**密碼要夠長、別外流**。
