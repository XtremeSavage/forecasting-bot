import asyncio
import httpx
from bot.config import load_settings
from bot.models import Forensics
from bot.stages import research


def test_extract_urls():
    t = "see https://example.com/a and http://b.org/x?y=1. Also https://c.net."
    assert research.extract_urls(t) == ["https://example.com/a", "http://b.org/x?y=1", "https://c.net"]


def test_html_to_text():
    html = open("tests/fixtures/resolution_page.html", encoding="utf-8").read()
    txt = research.html_to_text(html, 500)
    assert "2026-10-15" in txt and "menu" not in txt


async def test_fetch_resolution_sources_with_mock_transport():
    html = open("tests/fixtures/resolution_page.html", encoding="utf-8").read()

    def handler(request):
        if "bad" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, text=html)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = await research.fetch_resolution_sources(["https://good.example/x", "https://bad.example/y"], 5, 500, client=client)
    assert len(out) == 1 and out[0].provider == "resolution_source" and "2026-10-15" in out[0].text


async def test_run_isolates_provider_failures(monkeypatch):
    s = load_settings("config.yaml")
    s.research.asknews_enabled = True
    s.research.web_search_enabled = False
    s.research.resolution_fetch_enabled = False

    async def boom(queries, max_queries):
        raise RuntimeError("asknews down")

    monkeypatch.setattr(research, "asknews_search", boom)
    f = Forensics(resolution_statement="r", status_quo_outcome="No", search_queries=["q1"])
    bundle, cost = await research.run(llm=None, settings=s, forensics=f, criteria_text="", background_text="")
    assert bundle.sources == [] and "asknews" in bundle.diagnostics and cost == 0.0
