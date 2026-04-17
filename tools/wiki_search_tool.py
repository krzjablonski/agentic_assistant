import httpx
from tool_framework.i_tool import ITool, ToolResult, ToolParameter

# Registry of supported Fandom wikis: short name -> base URL
WIKI_REGISTRY = {
    "lovecraft": "https://lovecraft.fandom.com",
    "cthulhu": "https://lovecraft.fandom.com",
    "warhammer40k": "https://warhammer40k.fandom.com",
    "warhammer": "https://warhammerfantasy.fandom.com",
    "dnd": "https://forgottenrealms.fandom.com",
    "starwars": "https://starwars.fandom.com",
    "witcher": "https://witcher.fandom.com",
    "lotr": "https://lotr.fandom.com",
    "harrypotter": "https://harrypotter.fandom.com",
    "marvel": "https://marvel.fandom.com",
    "dc": "https://dc.fandom.com",
    "elderscrolls": "https://elderscrolls.fandom.com",
    "fallout": "https://fallout.fandom.com",
    "darksouls": "https://darksouls.fandom.com",
}


class WikiSearchTool(ITool):
    """Searches for articles on Fandom wikis using the MediaWiki API."""

    def __init__(self):
        available_wikis = ", ".join(sorted(WIKI_REGISTRY.keys()))
        super().__init__(
            name="search_wiki",
            description=(
                "Search for articles on a Fandom wiki. Returns ONLY article titles — you MUST then call get_wiki_page "
                "to read the actual content before answering the user. "
                "IMPORTANT: All wikis are in English, so ALWAYS translate your search query to English regardless of the user's language. "
                "Use this tool when you need to find information about fictional universes, games, movies, books, etc. "
                f"Available wikis: {available_wikis}"
            ),
            parameters=[
                ToolParameter(
                    name="wiki",
                    type="string",
                    required=True,
                    default=None,
                    description=(
                        f"Short name of the wiki to search. Available: {available_wikis}"
                    ),
                ),
                ToolParameter(
                    name="query",
                    type="string",
                    required=True,
                    default=None,
                    description="Search query in ENGLISH (translate if needed), e.g. 'Cthulhu', 'Darth Vader', 'Geralt of Rivia'",
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    required=False,
                    default=5,
                    description="Maximum number of results to return (default: 5, max: 10)",
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)

        wiki = args["wiki"].lower()
        query = args["query"]
        limit = min(args.get("limit", 5), 10)

        base_url = WIKI_REGISTRY.get(wiki)
        if not base_url:
            available = ", ".join(sorted(WIKI_REGISTRY.keys()))
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Unknown wiki '{wiki}'. Available wikis: {available}",
            )

        try:
            # Step 1: Search for matching page titles
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "srlimit": limit,
                        "srprop": "",
                        "format": "json",
                    },
                    timeout=15,
                )
            response.raise_for_status()
            data = response.json()

            search_results = data.get("query", {}).get("search", [])
            if not search_results:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"No results found for '{query}' on {wiki} wiki.",
                )

            titles = [item["title"] for item in search_results]

            # Step 2: Fetch short descriptions (intro extracts) for all found pages
            extracts = await self._fetch_extracts(base_url, titles)

            lines = [f"Found {len(titles)} result(s) on {wiki} wiki for '{query}':\n"]
            for i, title in enumerate(titles, 1):
                description = extracts.get(title, "No description available.")
                lines.append(f"{i}. **{title}** — {description}")

            lines.append(
                "\n>> NEXT STEP: Call get_wiki_page with the most relevant title above to read the full article before answering."
            )

            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="\n".join(lines),
            )

        except httpx.TimeoutException:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Request to {wiki} wiki timed out. Try again later.",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to search {wiki} wiki — {str(e)}",
            )

    async def _fetch_extracts(self, base_url: str, titles: list[str]) -> dict[str, str]:
        """Fetch short intro descriptions using action=parse (section 0, plain text)."""
        import re

        extracts = {}
        async with httpx.AsyncClient() as client:
            for title in titles:
                try:
                    response = await client.get(
                        f"{base_url}/api.php",
                        params={
                            "action": "parse",
                            "page": title,
                            "prop": "text",
                            "section": 0,
                            "format": "json",
                        },
                        timeout=10,
                    )
                    response.raise_for_status()
                    data = response.json()

                    html = data.get("parse", {}).get("text", {}).get("*", "")
                    if not html:
                        continue

                    # Strip HTML tags to get plain text
                    text = re.sub(r"<[^>]+>", " ", html)
                    text = re.sub(r"\s+", " ", text).strip()

                    # Take first 200 chars as description
                    if len(text) > 200:
                        text = text[:200].rsplit(" ", 1)[0] + "..."

                    if text:
                        extracts[title] = text
                except Exception:
                    continue

        return extracts
