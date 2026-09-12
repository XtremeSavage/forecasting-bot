from __future__ import annotations
import asyncio
import re
import httpx
from bot.config import Settings
from bot.models import Forensics, RawSource, ResearchBundle

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def extract_urls(text: str) -> list[str]:
    seen, out = set(), []
    for m in URL_RE.findall(text or ""):
        u = m.rstrip(".,;:")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def html_to_text(html: str, max_chars: int) -> str:
    try:
        import trafilatura
        txt = trafilatura.extract(html, include_comments=False, include_tables=True, favor_precision=True) or ""
    except Exception:  # noqa: BLE001
        txt = ""
    if not txt:
        txt = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:max_chars]


async def fetch_resolution_sources(urls: list[str], timeout_s: int, max_chars: int, client: httpx.AsyncClient | None = None) -> list[RawSource]:
    own = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=timeout_s, headers={"User-Agent": "Mozilla/5.0 (forecasting-bot)"})
    out: list[RawSource] = []
    try:
        for u in urls[:4]:
            try:
                r = await client.get(u)
                if r.status_code != 200:
                    continue
                text = html_to_text(r.text, max_chars)
                if text:
                    out.append(RawSource(provider="resolution_source", url=u, title=None, published=None, text=text))
            except Exception:  # noqa: BLE001
                continue
    finally:
        if own:
            await client.aclose()
    return out


async def asknews_search(queries: list[str], max_queries: int, timeout_s: int = 90) -> list[RawSource]:
    """One AskNews call per query, concurrently, with a per-query timeout.

    Queries run independently so a single slow or failing one costs only its own result
    instead of the whole provider (the old sequential loop under one outer timeout threw
    away every query that had already succeeded).
    """
    from forecasting_tools import AskNewsSearcher
    searcher = AskNewsSearcher()
    picked = list(queries)[:max_queries]

    async def one(q: str) -> RawSource | None:
        text = await asyncio.wait_for(searcher.get_formatted_news_async(q), timeout_s)
        return RawSource(provider="asknews", url=None, title=q, published=None, text=text) if text else None

    results = await asyncio.gather(*(one(q) for q in picked), return_exceptions=True)
    return [r for r in results if isinstance(r, RawSource)]


async def web_search(llm, settings: Settings, queries: list[str]) -> tuple[list[RawSource], float]:
    """One search-model call per query, concurrently, with a per-query timeout."""
    cfg = settings.research
    picked = list(queries)[: cfg.max_queries]

    async def one(q: str):
        prompt = (f"Search the web for: {q}\nReport the most relevant, most recent findings as bullet points. "
                  f"Each bullet: date (YYYY-MM-DD), the fact, and the source URL. Prefer official and primary sources. No speculation.")
        return await asyncio.wait_for(
            llm.complete(prompt, settings.models.web_search, temperature=0.1, max_tokens=1500), cfg.provider_timeout_s)

    results = await asyncio.gather(*(one(q) for q in picked), return_exceptions=True)
    out, cost = [], 0.0
    for q, res in zip(picked, results):
        if isinstance(res, BaseException):
            continue
        cost += res.cost_usd
        if res.text.strip():
            out.append(RawSource(provider="web_search", url=None, title=q, published=None, text=res.text[: cfg.source_text_max_chars]))
    return out, cost


async def run(llm, settings: Settings, forensics: Forensics, criteria_text: str, background_text: str) -> tuple[ResearchBundle, float]:
    cfg = settings.research
    queries = forensics.search_queries or []
    tasks: dict[str, asyncio.Task] = {}
    # asknews and web_search time out per query inside themselves and keep whatever
    # succeeded, so no outer timeout here - that one discarded partial results. The
    # resolution fetch has no internal per-item timeout, so it keeps its outer one.
    if cfg.asknews_enabled:
        tasks["asknews"] = asyncio.create_task(asknews_search(queries, cfg.max_queries, cfg.provider_timeout_s))
    if cfg.web_search_enabled and llm is not None:
        tasks["web_search"] = asyncio.create_task(web_search(llm, settings, queries))
    if cfg.resolution_fetch_enabled:
        urls = extract_urls(criteria_text) + [u for u in extract_urls(background_text) if u not in extract_urls(criteria_text)]
        tasks["resolution_source"] = asyncio.create_task(asyncio.wait_for(fetch_resolution_sources(urls, cfg.provider_timeout_s, cfg.source_text_max_chars), cfg.provider_timeout_s))
    bundle, cost = ResearchBundle(), 0.0
    for name, t in tasks.items():
        try:
            result = await t
        except Exception as e:  # noqa: BLE001
            bundle.diagnostics[name] = f"{type(e).__name__}: {e}"
            continue
        if name == "web_search":
            srcs, c = result
            cost += c
        else:
            srcs = result
        bundle.sources.extend(srcs)
    if tasks and not bundle.sources:
        # Research ran and came back with nothing at all: the forecast is about to be made
        # on the question text alone, which the record and the guards should say out loud.
        bundle.diagnostics["NO_RESEARCH"] = "all providers returned nothing"
    return bundle, cost
