---
name: web-research-routing
description: Use when a task in dj-track-similarity needs information from outside the checkout. Routes between built-in websearch/webfetch, tavily, and firecrawl, including audio-model literature for CLAP, MuQ, MuQ-MuLan, MERT, MAEST, and SONARA, and states how retrieved prose ranks against this checkout.
---

# Web Research Routing

- The configured providers are `tavily` and `firecrawl`; both spend API credits.
  Each harness wires them up its own way and exposes a different slice of
  Firecrawl, so route only to the tools named below, which every harness has.
  Start with built-in `websearch`/`webfetch` and escalate only when the built-in
  result is insufficient.
- Facts, news, or link discovery: `tavily_search`. Multi-source questions that
  need synthesis: `tavily_research`.
- Content of a known URL: `tavily_extract`, raising `extract_depth` to
  `advanced` for JS-rendered or protected pages.
- Schema-based structured extraction: read the page with `tavily_extract` and
  shape the fields yourself. No configured tool accepts an extraction schema.
- Site traversal: `tavily_map` for URLs, `tavily_crawl` for page content, each
  with an explicit `limit`.
- Library, API, and error questions: `firecrawl_search` with
  `categories: ["developer"]` over indexed GitHub issues, pull requests,
  READMEs, and documentation sites.
- Audio-model literature (CLAP, MuQ, MuQ-MuLan, MERT, MAEST, SONARA): the
  `firecrawl_research_*` tools, namely `firecrawl_research_search_papers`,
  `firecrawl_research_related_papers`, `firecrawl_research_inspect_paper`,
  `firecrawl_research_read_paper`, and `firecrawl_research_search_github`. These
  search paper abstracts and full text; `categories: ["research"]` on
  `firecrawl_search` is a different surface that only filters web results to
  research-affiliated sites. Name the paper ID with any claim taken from it.
- Retrieved prose never outranks this checkout. Executable sources and tests win
  on conflict, and retrieved model claims remain ranking evidence.
