#!/usr/bin/env python
"""Render the unified 考點地圖 (一試＋二試) as a self-contained Apple-style HTML file.

Usage:
    python scripts/render_topic_atlas.py [out.html]   # default: topic-atlas.html

Blue heat = how often a 考點 has been tested (MCQ+essay combined); 未考 topics
pop out in an orange dashed pill so "誰還沒考過" is obvious at a glance.
"""
from __future__ import annotations
import html
import sys
from pathlib import Path

from twexam_mcp.cache import db
from twexam_mcp.tools.exam_map import build_topic_atlas

_CSS = """
:root{ --bg:#f5f5f7; --card:#ffffff; --ink:#1d1d1f; --muted:#6e6e73;
  --blue:#0071e3; --orange:#ff9500; --line:#e3e3e8; }
*{ box-sizing:border-box; }
body{ margin:0; background:var(--bg); color:var(--ink); letter-spacing:-.01em;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,"PingFang TC","Microsoft JhengHei",sans-serif; }
.topbar{ position:sticky; top:0; z-index:9; padding:18px 28px;
  background:rgba(245,245,247,.78); backdrop-filter:saturate(180%) blur(20px);
  border-bottom:1px solid var(--line); display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
.topbar h1{ font-size:20px; margin:0; font-weight:600; }
.chips{ display:flex; gap:8px; flex-wrap:wrap; }
.chip{ font-size:13px; padding:5px 12px; border-radius:980px; background:#ececf0; color:var(--muted); font-weight:500; }
.chip b{ color:var(--ink); }
.chip.warn{ background:#fff2e0; color:#9a5b00; }
.wrap{ max-width:1180px; margin:0 auto; padding:26px 22px 80px; }
.legend{ display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin:6px 6px 26px;
  font-size:12.5px; color:var(--muted); }
.legend .sw{ display:inline-block; width:16px; height:16px; border-radius:5px; vertical-align:-3px; margin-right:5px; }
.sec-title{ font-size:15px; font-weight:600; color:var(--muted); margin:34px 6px 14px; text-transform:none; }
.card{ background:var(--card); border:1px solid var(--line); border-radius:18px;
  padding:18px 20px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.04); }
.card h3{ margin:0 0 4px; font-size:16px; font-weight:600; }
.card .meta{ font-size:12.5px; color:var(--muted); margin-bottom:12px; }
.group{ margin:12px 0; }
.group .gname{ font-size:13px; font-weight:600; color:#3a3a3c; margin:8px 0 8px; }
.tiles{ display:flex; flex-wrap:wrap; gap:8px; }
.tile{ position:relative; padding:8px 12px; border-radius:12px; font-size:13.5px; font-weight:500;
  border:1px solid transparent; cursor:default; transition:transform .08s ease; }
.tile:hover{ transform:translateY(-1px); }
.tile .n{ font-weight:700; margin-left:6px; opacity:.9; }
/* blue heat buckets */
.h0{ background:#fff7ed; border:1.5px dashed var(--orange); color:#9a5b00; }
.h0 .tag{ margin-left:7px; font-size:11px; font-weight:700; color:#fff; background:var(--orange);
  padding:1px 7px; border-radius:980px; }
.h1{ background:#eaf3fe; color:#0b3a66; }
.h2{ background:#c2e0fd; color:#0b3a66; }
.h3{ background:#7fbef9; color:#06294d; }
.h4{ background:#2f93f0; color:#fff; }
.h5{ background:#0a5fc2; color:#fff; }
.tip{ position:fixed; pointer-events:none; z-index:30; background:#1d1d1f; color:#fff;
  font-size:12px; padding:7px 10px; border-radius:9px; opacity:0; transition:opacity .1s; white-space:nowrap;
  box-shadow:0 6px 20px rgba(0,0,0,.25); }
.uncovered-note{ background:#fff; border:1px solid var(--line); border-radius:18px; padding:16px 20px;
  margin-bottom:10px; box-shadow:0 1px 3px rgba(0,0,0,.04); }
.uncovered-note h3{ margin:0 0 10px; font-size:15px; }
.uncovered-note .tiles .tile{ cursor:default; }
"""

_JS = """
const tip=document.querySelector('.tip');
document.querySelectorAll('.tile[data-tip]').forEach(el=>{
  el.addEventListener('mousemove',e=>{ tip.textContent=el.dataset.tip; tip.style.opacity=1;
    tip.style.left=(e.clientX+12)+'px'; tip.style.top=(e.clientY+14)+'px'; });
  el.addEventListener('mouseleave',()=>{ tip.style.opacity=0; });
});
"""


def _heat(total: int) -> str:
    if total == 0: return "h0"
    if total <= 4: return "h1"
    if total <= 12: return "h2"
    if total <= 30: return "h3"
    if total <= 60: return "h4"
    return "h5"


def _tile(t: dict) -> str:
    name = html.escape(t["topic"])
    tip = f"選擇 {t['mcq']}・申論 {t['essay']}・最後 {t['last_year'] or '—'} 年"
    cls = _heat(t["total"])
    if t["total"] == 0:
        inner = f'{name}<span class="tag">未考</span>'
    else:
        inner = f'{name}<span class="n">{t["total"]}</span>'
    return f'<span class="tile {cls}" data-tip="{html.escape(tip)}">{inner}</span>'


def render(atlas: dict) -> str:
    s = atlas["summary"]
    parts: list[str] = []
    parts.append('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("<title>考點地圖 · 司律一試＋二試</title>")
    parts.append(f"<style>{_CSS}</style></head><body>")
    # topbar
    parts.append('<div class="topbar"><h1>考點地圖 · 司律一試＋二試</h1><div class="chips">')
    parts.append(f'<span class="chip"><b>{s["total_topics"]}</b> 考點</span>')
    parts.append(f'<span class="chip"><b>{s["examined"]}</b> 已考</span>')
    parts.append(f'<span class="chip warn"><b>{s["uncovered_count"]}</b> 還沒考過</span>')
    parts.append(f'<span class="chip"><b>{s["total_questions"]}</b> 題</span>')
    parts.append("</div></div>")
    parts.append('<div class="wrap">')
    # legend
    parts.append('<div class="legend">熱度（選擇＋申論合計）：'
                 '<span><span class="sw" style="background:#eaf3fe"></span>1–4</span>'
                 '<span><span class="sw" style="background:#c2e0fd"></span>5–12</span>'
                 '<span><span class="sw" style="background:#7fbef9"></span>13–30</span>'
                 '<span><span class="sw" style="background:#2f93f0"></span>31–60</span>'
                 '<span><span class="sw" style="background:#0a5fc2"></span>61+</span>'
                 '<span style="margin-left:8px"><span class="sw" style="background:#fff7ed;'
                 'border:1.5px dashed #ff9500"></span>還沒考過</span></div>')
    # uncovered highlight box (answers 「誰還沒考過」at a glance)
    parts.append('<div class="uncovered-note"><h3>🆕 最新還沒考過的考點（'
                 f'{s["uncovered_count"]}）</h3><div class="tiles">')
    for name in s["uncovered"]:
        parts.append(f'<span class="tile h0">{html.escape(name)}<span class="tag">未考</span></span>')
    parts.append("</div></div>")
    # sections
    for sec in atlas["sections"]:
        parts.append(f'<div class="sec-title">{html.escape(sec["label"])}</div>')
        for subj in sec["subjects"]:
            tot = sum(t["total"] for g in subj["groups"] for t in g["topics"])
            parts.append('<div class="card">')
            parts.append(f'<h3>{html.escape(subj["subject"])}</h3>')
            parts.append(f'<div class="meta">合計 {tot} 題</div>')
            for g in subj["groups"]:
                parts.append('<div class="group">')
                if g["name"]:
                    parts.append(f'<div class="gname">{html.escape(g["name"])}</div>')
                parts.append('<div class="tiles">')
                parts.extend(_tile(t) for t in g["topics"])
                parts.append("</div></div>")
            parts.append("</div>")
    parts.append("</div>")  # wrap
    parts.append('<div class="tip"></div>')
    parts.append(f"<script>{_JS}</script></body></html>")
    return "".join(parts)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    out = Path(argv[0]) if argv else Path("topic-atlas.html")
    conn = db.connect(db.default_db_path())
    atlas = build_topic_atlas(conn)
    out.write_text(render(atlas), encoding="utf-8")
    s = atlas["summary"]
    print(f"[atlas] {s['total_topics']} 考點 | {s['examined']} 已考 | "
          f"{s['uncovered_count']} 還沒考過 | {s['total_questions']} 題")
    print(f"[atlas] wrote {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
