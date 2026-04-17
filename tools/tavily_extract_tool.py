import httpx
from config_service import config_service
from tool_framework.i_tool import ITool, ToolResult, ToolParameter


class TavilyExtractTool(ITool):
    """Extracts web page content from one or more specified URLs using Tavily API."""

    def __init__(self):
        super().__init__(
            name="tavily_extract",
            description="Extracts raw markdown or text web page content from one or more specified URLs. Ideal for deep-diving into specific web pages found via search.",
            parameters=[
                ToolParameter(
                    name="urls",
                    type="list",
                    required=True,
                    default=None,
                    description="A list of URLs to extract content from. Must be a valid list of strings.",
                ),
            ],
        )

    async def run(self, args: dict[str, any]) -> ToolResult:
        self.validate_parameters(args)

        urls = args.get("urls", [])
        if not urls:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: No URLs provided for extraction.",
                is_error=True,
            )

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
            "urls": urls,
            "format": "markdown",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/extract",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
            response.raise_for_status()
            data = response.json()

            result_lines = []

            results = data.get("results", [])
            for res in results:
                url = res.get("url", "")
                raw_content = res.get("raw_content", "")
                result_lines.append(f"URL: {url}")
                result_lines.append(f"Content:\n{raw_content}")
                result_lines.append("\n=========================================\n")

            failed_results = data.get("failed_results", [])
            if failed_results:
                result_lines.append(
                    "Failed to extract content from the following URLs:"
                )
                for failed_res in failed_results:
                    url = failed_res.get("url", "")
                    error = failed_res.get("error", "Unknown error")
                    result_lines.append(f"- {url}: {error}")

            final_result = "\n".join(result_lines)
            if not final_result.strip():
                final_result = "No extract results returned by the API."

            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=final_result,
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to extract content using Tavily — {str(e)}",
                is_error=True,
            )
