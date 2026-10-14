# External research routing

Read when the task needs external facts, documentation, upstream behavior,
papers or web extraction.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## WEB RESEARCH ROUTING

- Establish checkout-specific facts from local source, manifests, locks and
  installed help first. For upstream behavior, identify the relevant package
  version or model revision before choosing documentation; distinguish that
  pinned behavior from newer upstream releases.

### Tool selection

- Start with Perplexity search/ask when it is available, otherwise built-in web
  search/page reading. Use Context7 for library and API documentation. Use
  Tavily or Firecrawl when those results are insufficient; account for their
  API-credit costs. Discover the tools available in the current session and
  follow the provider's own skills/help rather than assuming fixed tool names or
  capabilities.
- Use Tavily search for facts, news and links, research for multi-source
  synthesis, and extraction for known URLs. For difficult or JS-rendered pages,
  use the provider's supported advanced extraction or browser workflow.
- Use map for URL discovery and crawl for page content, with explicit limits.
  For structured extraction, use a supported schema workflow or shape fields
  from extracted content when that capability is unavailable.
- For library/API behavior and errors beyond Context7, use Firecrawl's developer
  index when available to locate official documentation, repository issues and
  PRs.
- For audio-model literature (CLAP, MuQ, MuQ-MuLan, MERT-v2, MAEST, SONARA), use
  the research-paper index when available, inspect relevant papers and linked
  repositories, and cite the paper URL or ID for claims. A web-search research
  category is not equivalent to searching a paper index or reading full text.
- For Firecrawl CLI output, pass an explicit `--output` under
  `.workspace/tools/firecrawl/`, never the default root-level `.firecrawl/`.

### Evidence and reporting

- Use search results to locate primary sources: official documentation,
  upstream code, issue/PR discussions and papers. Read the source supporting
  a consequential claim and cite it directly; distinguish documented behavior,
  proposed changes and your own inference.
- Retrieved prose does not override executable source/tests about this checkout;
  model claims remain ranking evidence.
