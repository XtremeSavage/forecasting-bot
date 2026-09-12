import httpx
import pytest
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

    async def boom(queries, max_queries, timeout_s=90):
        raise RuntimeError("asknews down")

    monkeypatch.setattr(research, "asknews_search", boom)
    f = Forensics(resolution_statement="r", status_quo_outcome="No", search_queries=["q1"])
    bundle, cost = await research.run(llm=None, settings=s, forensics=f, criteria_text="", background_text="")
    assert bundle.sources == [] and "asknews" in bundle.diagnostics and cost == 0.0
    assert bundle.diagnostics["NO_RESEARCH"] == "all providers returned nothing"


class _PartialLlm:
    """Succeeds on every query but q2."""

    def __init__(self):
        self.calls = 0

    async def complete(self, prompt, model, temperature=0.5, system=None, max_tokens=4000):
        from bot.llm import LlmResult
        self.calls += 1
        if "q2" in prompt:
            raise RuntimeError("search provider blew up on q2")
        return LlmResult(text="a finding", model=model, cost_usd=0.01, prompt_tokens=1, completion_tokens=1, provider="openrouter")


async def test_web_search_keeps_results_from_the_queries_that_worked():
    # Queries run concurrently and independently: one failure must not discard the rest,
    # which is what the old sequential loop under a single outer timeout did.
    s = load_settings("config.yaml")
    llm = _PartialLlm()
    out, cost = await research.web_search(llm, s, ["q1", "q2", "q3"])
    assert [o.title for o in out] == ["q1", "q3"]
    assert llm.calls == 3
    assert cost == pytest.approx(0.02)


async def test_no_research_diagnostic_when_enabled_providers_return_nothing(monkeypatch):
    s = load_settings("config.yaml")
    s.research.asknews_enabled = True
    s.research.web_search_enabled = False
    s.research.resolution_fetch_enabled = False

    async def empty(queries, max_queries, timeout_s=90):
        return []

    monkeypatch.setattr(research, "asknews_search", empty)
    f = Forensics(resolution_statement="r", status_quo_outcome="No", search_queries=["q1"])
    bundle, cost = await research.run(llm=None, settings=s, forensics=f, criteria_text="", background_text="")
    assert bundle.sources == []
    assert bundle.diagnostics["NO_RESEARCH"] == "all providers returned nothing"


async def test_no_research_diagnostic_absent_when_every_provider_is_off():
    s = load_settings("config.yaml")
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    f = Forensics(resolution_statement="r", status_quo_outcome="No", search_queries=["q1"])
    bundle, cost = await research.run(llm=None, settings=s, forensics=f, criteria_text="", background_text="")
    assert bundle.diagnostics == {}
