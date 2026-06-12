# tests/test_downloader.py
from pathlib import Path
from twexam_mcp.ingest import downloader, refs


def test_cache_path_is_stable(tmp_path):
    ref = refs.SubjectRef("113110", "301", "0101", "1")
    p = downloader.cache_path(tmp_path, ref, "Q")
    assert p == tmp_path / "113110" / "Q_c301_s0101_q1.pdf"


def test_download_uses_cache(tmp_path, monkeypatch):
    ref = refs.SubjectRef("113110", "301", "0101", "1")
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return b"%PDF-stub"

    monkeypatch.setattr(downloader, "_http_get", fake_fetch)
    p1 = downloader.download(tmp_path, ref, "Q")
    p2 = downloader.download(tmp_path, ref, "Q")   # second call hits cache
    assert p1.read_bytes() == b"%PDF-stub"
    assert len(calls) == 1   # only fetched once
