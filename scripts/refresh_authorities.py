#!/usr/bin/env python
"""實務見解字號「時效性」盤點：列出「待驗(MISSING)」與「已驗待回查(CACHED)」的字號。

【為什麼是這種設計】與 refresh_statutes.py 同——topic-atlas.html 是 file:// 靜態檔，
瀏覽器端不能即時打法規庫/憲法法庭 API，故「是否仍為有效見解」只能在刷新時查，本程序負責
「盤點」，實際查驗由具 taiwan-legal-db 的 agent（或 /schedule 排程 agent）執行：

刷新一輪（agent 或排程）：
  1. python scripts/refresh_authorities.py          # 看 MISSING（待驗）/ CACHED（已驗）
  2. 對 MISSING 逐筆查 taiwan-legal-db：
       釋字 / 憲判 → get_interpretation（憲判取代釋字者於此可見）
       台上/台抗/台非… → search_judgments（判例是否「停止適用」、見解是否經大法庭變更）
     寫入 twexam_mcp/data/authorities.json，status ∈
       {現行有效, 停止適用, 被憲判取代, 見解經大法庭變更, 待查}
  3. 對 CACHED 重查 → status 變動即更新
  4. python scripts/render_atlas.py                 # 過期字號標紅；commit

用法：python scripts/refresh_authorities.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from authority_refs import extract_authorities  # noqa: E402
from twexam_mcp.cache import db  # noqa: E402

_STATUS_OK = {"現行有效", None}


def collect(conn) -> dict:
    """key -> {type, canons:set}：全部被引用的實務字號，及引用它的爭點。"""
    found: dict[str, dict] = {}

    def add(text, canon):
        for typ, key in extract_authorities(text):
            e = found.setdefault(key, {"type": typ, "canons": set()})
            e["canons"].add(canon)

    rows = conn.execute(
        "SELECT COALESCE(c.canonical, e.issue), e.practice "
        "FROM essay_issues e LEFT JOIN issue_canon c ON c.issue = e.issue"
    )
    for canon, prac in rows:
        for p in json.loads(prac or "[]"):
            add(p, canon)

    ip_path = db.default_db_path().parent / "issue_primers.json"
    ip = json.loads(ip_path.read_text(encoding="utf-8")) if ip_path.exists() else {}
    for canon, d in ip.items():
        add(d.get("primer", "") or "", canon)
        for a in (d.get("answers") or {}).values():
            add(a, canon)
    return found


def main(argv=None) -> int:
    conn = db.connect(db.default_db_path())
    db.init_schema(conn)
    db.apply_issue_canon(conn)
    db.apply_essay_issues(conn)

    apath = db.default_db_path().parent / "authorities.json"
    cached = json.loads(apath.read_text(encoding="utf-8")) if apath.exists() else {}

    found = collect(conn)
    missing = sorted(k for k in found if k not in cached)
    present = sorted(k for k in found if k in cached)

    by_type: dict[str, list] = {}
    for k in missing:
        by_type.setdefault(found[k]["type"], []).append(k)

    print(f"[authorities] 引用字號 {len(found)} 個 ｜ 已驗 {len(present)} ｜ 待驗 {len(missing)}")
    for typ in ("釋字", "憲判", "法院", "決議"):
        ks = by_type.get(typ, [])
        if ks:
            shown = "、".join(ks[:30]) + (" …" if len(ks) > 30 else "")
            print(f"  MISSING·{typ}（{len(ks)}）：{shown}")

    stale = [k for k in present if cached[k].get("status") not in _STATUS_OK]
    if stale:
        print(f"  ⚠ 已標非現行有效（{len(stale)}）：" +
              "、".join(k + "=" + str(cached[k].get("status")) for k in stale))

    print("\n下一步：對 MISSING 用 taiwan-legal-db 查驗 → 寫 authorities.json（流程見檔頭）。")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
