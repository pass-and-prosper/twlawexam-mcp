#!/usr/bin/env python
"""法條現行版維護：列出「該收錄但尚未收錄」與「已收錄待回查時效」的條文。

【為什麼是這種設計】topic-atlas.html 是 file:// 純靜態檔，瀏覽器端不能即時打法規庫 API，
故「動態檢查是不是最新」只能在產製/刷新時做：本程序負責「盤點」，實際抓取/比對由具
legal-db MCP 的 agent（或 /schedule 排程 agent）執行——這是唯一能讀全國法規資料庫的角色。

刷新一輪（agent 或排程）：
  1. python scripts/refresh_statutes.py            # 看缺哪些條（MISSING）、已收錄哪些（CACHED）
  2. 對 MISSING 逐條呼叫 taiwan-legal-db query_regulation → 寫入 twexam_mcp/data/statutes.json
  3. 對 CACHED 重查 → 若回傳 content 與快取不同（表示法規已修正）或 status 非「現行法規」→ 更新並標記
  4. python scripts/render_atlas.py                # 重新產製；commit

時效判定＝以「重查 content 是否變動」為準（content 變 = 已修法 = 該更新），不需解析中文修法日期。

用法：
  python scripts/refresh_statutes.py            # 報告（預設）
  python scripts/refresh_statutes.py --check    # 額外印出 CACHED 條文供 agent 比對
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from statute_refs import stable_key, SUBJECT_DEFAULT  # noqa: E402

# render_atlas 與本檔共用抽取邏輯
import render_atlas as ra  # noqa: E402
from twexam_mcp.cache import db  # noqa: E402


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    show_cached = "--check" in argv

    conn = db.connect(db.default_db_path())
    db.init_schema(conn)
    db.apply_issue_canon(conn)
    db.apply_essay_issues(conn)

    spath = db.default_db_path().parent / "statutes.json"
    statutes = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {}

    # 蒐集全部被引用的 (法規,條號)
    needed: dict[str, tuple[str, str]] = {}   # key -> (法規,條號)
    by_canon: dict[str, set[str]] = {}
    for canon, subj, refs in ra.iter_issue_refs(conn):
        for law, art in refs:
            k = stable_key(law, art)
            needed[k] = (law, art)
            by_canon.setdefault(canon, set()).add(k)

    missing = sorted(k for k in needed if k not in statutes)
    cached = sorted(k for k in needed if k in statutes)
    orphan = sorted(k for k in statutes if k not in needed)  # 收錄了但已無人引用

    print(f"[statutes] 引用法條 {len(needed)} 條 | 已收錄 {len(cached)} | 缺 {len(missing)} | 孤兒(無引用) {len(orphan)}")
    print(f"[statutes] 可自動解析科目(裸§)：{', '.join(SUBJECT_DEFAULT)}（其餘科目裸§已略過，須明確前綴）")

    if missing:
        print("\n--- MISSING（請對下列逐條 query_regulation 後寫入 statutes.json）---")
        bylaw: dict[str, list[str]] = {}
        for k in missing:
            law, art = needed[k]
            bylaw.setdefault(law, []).append(art)
        for law in sorted(bylaw):
            arts = sorted(bylaw[law], key=lambda a: (int(a.split("-")[0]), a))
            print(f"  {law}：{'、'.join(arts)}")

    if orphan:
        print("\n--- ORPHAN（已收錄但目前無爭點引用，可保留或清理）---")
        print("  " + "、".join(orphan))

    if show_cached:
        print("\n--- CACHED（重查 content 比對是否變動；不同=已修法=更新）---")
        for k in cached:
            s = statutes[k]
            print(f"  {k}  fetched={s.get('fetched','?')}  status={s.get('status','?')}")
            print(f"    {s.get('content','')}")

    # 退出碼：有缺漏回 2（方便 CI/排程判斷需要刷新），全到齊回 0
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
