import httpx
from config_service import config_service
from tool_framework.i_tool import ITool, ToolResult, ToolParameter


class TavilySearchTool(ITool):
    """Executes a search query using Tavily API. Use this tool to search the web for current information."""

    def __init__(self):
        super().__init__(
            name="tavily_search",
            description="Searches the web for up-to-date information. Returns concise search results and optionally an AI generated answer or raw webpage content.",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    required=True,
                    default=None,
                    description="The search query to execute, e.g., 'Who is Leo Messi?' or 'Latest AI news'.",
                ),
                ToolParameter(
                    name="search_depth",
                    type="string",
                    required=False,
                    default="basic",
                    description="Tradeoff between latency and relevance. Use 'basic' for general queries, 'advanced' for deeper research.",
                ),
            ],
        )

    async def run(self, args: dict[str, any]) -> ToolResult:
        self.validate_parameters(args)

        query = args.get("query")
        search_depth = args.get("search_depth", "basic")
        include_answer = False
        include_raw_content = False

        api_key = config_service.get("web_search.tavily_api_key")
        if not api_key:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: TAVILY_API_KEY environment variable is not set.",
                is_error=True,
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "query": query,
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
            response.raise_for_status()
            data = response.json()

            result_lines = []

            if include_answer and "answer" in data and data["answer"]:
                result_lines.append(f"Answer: {data['answer']}\n")

            results = data.get("results", [])
            for res in results:
                title = res.get("title", "")
                url = res.get("url", "")
                content = res.get("content", "")

                result_lines.append(f"Title: {title}")
                result_lines.append(f"URL: {url}")
                result_lines.append(f"Content snippet: {content}")

                if include_raw_content and res.get("raw_content"):
                    result_lines.append(f"Raw content: {res['raw_content']}")

                result_lines.append("---")

            final_result = "\n".join(result_lines)
            if not final_result.strip():
                final_result = "No results found for the query."

            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=final_result,
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to fetch search results from Tavily — {str(e)}",
                is_error=True,
            )
