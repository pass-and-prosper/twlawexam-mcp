#!/usr/bin/env python
"""月度刷新：偵測新權威材料(新憲判字/新釋字/新考季)，有變動才值得重跑 5 來源預測研究。

為什麼不是傳統爬蟲：預測爭點的「學說對立＋實務字號＋為何可能考」是 LLM-agent
研究(web + taiwan-legal-db 驗證)產出的，純抓網頁做不出來。月度會動的硬訊號是
憲判字/大法庭/期刊；本腳本做「便宜偵測」，把要不要重跑(較貴)的決定權交給你。

用法：
  python scripts/refresh_predictions.py            # 偵測+通知+更新快照(月排程跑這個)
  python scripts/refresh_predictions.py --render   # 順便重生 topic-atlas.html
  python scripts/refresh_predictions.py --research  # 偵測到新材料時，呼叫 headless
                                                    # claude 重跑研究(需 claude CLI；best-effort)

排程(每月1號 09:00，本機 Task Scheduler)：見 README / 下方 register 範例。
推送一律手動(隱私紅線)；pre-push hook 會把關。
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from twexam_mcp.cache import db

# 5 個預測來源：①研究推測 ②高普考 ③法律系/PTT(期中期末考) ④期刊論文。
# 連續源(每月本來就會長新東西、無法靠版本號偵測，月度一律重爬)：期刊、法律系/PTT。
# 硬觸發源(有明確版本可偵測)：憲判字、釋字、考季(新題庫年度)。
_CONTINUOUS_SOURCES = "期刊論文、法律系/PTT(期中期末考)"
# 大學考季月份(期中 4/11、期末 1/6) → 該月特別可能有新期中期末考上 PTT
_EXAM_SEASON_MONTHS = {1, 4, 6, 11}

# 司法院釋字/憲判字本地快取(taiwan-legal-db)。可用環境變數覆寫路徑。
_LEGAL_DIR = Path(os.environ.get(
    "TWLEGAL_DATA", r"W:/FastAPI/mcp-taiwan-legal-db/mcp_server/data"))
_STATE = Path(__file__).resolve().parent.parent / ".refresh_state.json"
_PENDING = Path(__file__).resolve().parent.parent / "_pending_refresh.md"
_REFRESH_PROMPT = Path(__file__).resolve().parent.parent / "docs" / "refresh-predictions-prompt.md"


def _load_json(p: Path, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def current_authority() -> dict:
    """本地可查的權威材料快照（不連網、不依賴會被擋的站點）。"""
    snap = {"exam_max_year": None, "interpretation_count": 0, "constitutional": []}
    conn = db.connect(db.default_db_path())
    row = conn.execute("SELECT MAX(year) FROM questions").fetchone()
    snap["exam_max_year"] = row[0] if row else None
    old = _load_json(_LEGAL_DIR / "old_cases.json", {})          # 釋字 1..813
    new = _load_json(_LEGAL_DIR / "new_cases.json", {})          # 憲判字 {year_num: {...}}
    snap["interpretation_count"] = len(old)
    snap["constitutional"] = sorted(new.keys())
    return snap


def detect(prev: dict, cur: dict) -> dict:
    """回傳自上次以來的新材料。"""
    prev_const = set(prev.get("constitutional", []))
    new_const = [k for k in cur["constitutional"] if k not in prev_const]
    return {
        "new_exam_year": (cur["exam_max_year"] if cur["exam_max_year"] != prev.get("exam_max_year")
                          and prev.get("exam_max_year") is not None else None),
        "new_constitutional": new_const,            # 新憲判字 (year_num keys)
        "new_interpretations": max(0, cur["interpretation_count"] - prev.get("interpretation_count", 0)),
        "first_run": not prev,
    }


def _notify(title: str, msg: str) -> None:
    """Windows 桌面通知（失敗就略過，仍會寫 _pending_refresh.md / log）。"""
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null;"
        "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        f"$t.GetElementsByTagName('text')[0].AppendChild($t.CreateTextNode('{title}'))|Out-Null;"
        f"$t.GetElementsByTagName('text')[1].AppendChild($t.CreateTextNode('{msg}'))|Out-Null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('twexam')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($t))"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=20,
                       capture_output=True)
    except Exception:
        pass


def _run_research() -> bool:
    """有新材料時，呼叫 headless claude 重跑 5 來源研究(best-effort)。需 claude CLI。"""
    if not _REFRESH_PROMPT.exists():
        print(f"[refresh] 找不到 {_REFRESH_PROMPT}，略過自動重跑研究")
        return False
    prompt = _REFRESH_PROMPT.read_text(encoding="utf-8")
    try:
        subprocess.run(["claude", "-p", prompt], cwd=str(_REFRESH_PROMPT.parent.parent),
                       timeout=3600)
        return True
    except FileNotFoundError:
        print("[refresh] 找不到 claude CLI，無法自動重跑；請手動跑 /refresh-predictions")
        return False
    except Exception as e:
        print(f"[refresh] 自動重跑失敗：{e}")
        return False


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    prev = _load_json(_STATE, {})
    cur = current_authority()
    d = detect(prev, cur)

    new_const = d["new_constitutional"]
    season = date.today().month in _EXAM_SEASON_MONTHS
    hard = bool(new_const) or d["new_exam_year"] or d["new_interpretations"]
    lines = [
        "# 月度預測刷新報告",
        f"- 連續源(每月一律重爬)：{_CONTINUOUS_SOURCES}"
        + ("  ★ 本月為大學考季，期中/期末考較可能上 PTT" if season else ""),
        f"- 題庫最新年度：{cur['exam_max_year']}"
        + (f"  ⚠️ 新考季！(原 {prev.get('exam_max_year')})" if d["new_exam_year"] else ""),
        f"- 釋字數：{cur['interpretation_count']}"
        + (f"  ⚠️ +{d['new_interpretations']}" if d["new_interpretations"] else ""),
        f"- 憲判字數：{len(cur['constitutional'])}"
        + (f"  ⚠️ 新增 {len(new_const)} 件：{new_const}" if new_const else ""),
    ]
    report = "\n".join(lines)
    print(report)

    if d["first_run"]:
        print("[refresh] 首次執行，僅建立快照基準（不觸發重跑）")
    else:
        # 期刊 + 法律系/PTT 是連續源，每月都值得重爬；憲判字/新考季是額外硬觸發。
        why = ["連續源(期刊/法律系PTT)"]
        if hard:
            why.append("＋硬訊號(新憲判字/考季)")
        if season:
            why.append("＋大學考季")
        _PENDING.write_text(report + f"\n\n→ 本月可刷新預測（{''.join(why)}）："
                            "手動 /refresh-predictions 或本腳本 --research。\n", encoding="utf-8")
        _notify("twexam 預測可刷新",
                f"連續源+{'新憲判字'+str(len(new_const)) if new_const else ('考季' if season else '常規')}")
        if "--research" in argv:
            _run_research()

    _STATE.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")

    if "--render" in argv:
        from scripts import render_atlas  # noqa
        render_atlas.main(["topic-atlas.html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
