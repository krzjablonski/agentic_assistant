import httpx
from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from tools.wiki_search_tool import WIKI_REGISTRY


class WikiPageTool(ITool):
    """Retrieves the content of a specific article from a Fandom wiki."""

    def __init__(self):
        available_wikis = ", ".join(sorted(WIKI_REGISTRY.keys()))
        super().__init__(
            name="get_wiki_page",
            description=(
                "Get the content of a specific article from a Fandom wiki. "
                "Use this after search_wiki to read full article content. "
                "Returns plain text of the article, truncated to max_chars."
            ),
            parameters=[
                ToolParameter(
                    name="wiki",
                    type="string",
                    required=True,
                    default=None,
                    description=(
                        f"Short name of the wiki. Available: {available_wikis}"
                    ),
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    required=True,
                    default=None,
                    description="Exact title of the article (as returned by search_wiki), e.g. 'Cthulhu'",
                ),
                ToolParameter(
                    name="max_chars",
                    type="integer",
                    required=False,
                    default=3000,
                    description="Maximum number of characters to return (default: 3000). Increase for longer articles.",
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)

        wiki = args["wiki"].lower()
        title = args["title"]
        max_chars = args.get("max_chars", 3000)

        base_url = WIKI_REGISTRY.get(wiki)
        if not base_url:
            available = ", ".join(sorted(WIKI_REGISTRY.keys()))
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Unknown wiki '{wiki}'. Available wikis: {available}",
            )

        # Try 'extracts' first (returns clean plain text)
        content = await self._try_extracts(base_url, title)

        # Fallback to 'parse' if extracts didn't work
        if content is None:
            content = await self._try_parse(base_url, title)

        if content is None:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Could not retrieve article '{title}' from {wiki} wiki. The page may not exist.",
            )

        # Truncate if necessary
        if len(content) > max_chars:
            content = (
                content[:max_chars]
                + "\n\n[... article truncated. Use a higher max_chars to see more.]"
            )

        header = f"=== {title} ({wiki} wiki) ===\n\n"
        return ToolResult(
            tool_name=self.name,
            parameters=args,
            result=header + content,
        )

    async def _try_extracts(self, base_url: str, title: str) -> str | None:
        """Try the TextExtracts API (returns clean plain text)."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/api.php",
                    params={
                        "action": "query",
                        "titles": title,
                        "prop": "extracts",
                        "explaintext": "true",
                        "format": "json",
                    },
                    timeout=15,
                )
            response.raise_for_status()
            data = response.json()

            pages = data.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                if page_id == "-1":
                    return None
                extract = page_data.get("extract", "")
                if extract:
                    return extract.strip()

            return None
        except Exception:
            return None

    async def _try_parse(self, base_url: str, title: str) -> str | None:
        """Fallback: use action=parse to get wikitext and strip markup."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/api.php",
                    params={
                        "action": "parse",
                        "page": title,
                        "prop": "wikitext",
                        "format": "json",
                    },
                    timeout=15,
                )
            response.raise_for_status()
            data = response.json()

            wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
            if not wikitext:
                return None

            return self._clean_wikitext(wikitext)
        except Exception:
            return None

    @staticmethod
    def _clean_wikitext(text: str) -> str:
        """Basic cleanup of MediaWiki markup to produce readable plain text."""
        import re

        # Remove templates like {{...}} (non-greedy, handles simple cases)
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
        # Remove remaining nested templates (second pass)
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)

        # Convert wiki links [[Target|Display]] -> Display, [[Target]] -> Target
        text = re.sub(r"\[\[[^|\]]*\|([^\]]+)\]\]", r"\1", text)
        text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)

        # Remove external links [http://... Display] -> Display
        text = re.sub(r"\[https?://[^\s\]]+ ([^\]]+)\]", r"\1", text)
        text = re.sub(r"\[https?://[^\]]+\]", "", text)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Convert headings == Title == -> Title
        text = re.sub(r"={2,}\s*(.+?)\s*={2,}", r"\n\1\n", text)

        # Remove bold/italic markup
        text = re.sub(r"'{2,5}", "", text)

        # Remove category links
        text = re.sub(r"\[\[Category:[^\]]+\]\]", "", text, flags=re.IGNORECASE)

        # Remove file/image links
        text = re.sub(r"\[\[File:[^\]]+\]\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[\[Image:[^\]]+\]\]", "", text, flags=re.IGNORECASE)

        # Clean up excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"  +", " ", text)

        return text.strip()
