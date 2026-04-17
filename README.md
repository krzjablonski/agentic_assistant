# AI Agent (ReAct Pattern)

An AI agent built on the **ReAct** (Reasoning + Acting) pattern. The agent iteratively reasons about a problem, uses tools to gather information or perform actions, observes results, and repeats until it can provide a final answer.

**Key Features:**

- Supports multiple LLM providers (Anthropic, Gemini, and OpenAI-compatible backends).
- Extensible tool system with dynamic tool selection in the UI.
- **MCP support** — connect to external tool servers via Model Context Protocol.
- Secure configuration management via an encrypted Settings UI.
- Memory system (token-aware short-term context & long-term persistence).
- Multimodal support (image inputs in the Streamlit web UI).
- Built-in logging and a lightweight dashboard for inspecting runs and AI Devs exercises.

## Project Structure

```
├── src/
│   ├── agent/
│   │   ├── i_agent.py                  # Abstract agent base class, message/content block types, and conversation primitives
│   │   ├── agent_event.py              # Agent event model and event types
│   │   ├── agent_factory.py            # Builder for assembling agents, LLM clients, logging, and config
│   │   ├── message_factory.py          # Helper for converting dicts to Message objects
│   │   ├── prompts/
│   │   │   └── react_prompts.py        # System prompt, self-reflection prompt, and planning prompts
│   │   └── simple_agent/
│   │       ├── simple_agent.py         # ReAct agent implementation (SimpleAgent, AgentConfig, AgentStatus)
│   │       └── agent_plan.py           # Plan data structures (AgentPlan, PlanStep, PlanStepStatus)
│   ├── config_service/
│   │   ├── config_service.py           # Encrypted SQLite-backed configuration service
│   │   └── config.py                   # Lightweight compatibility layer for config lookups
│   ├── llm/
│   │   ├── i_llm_client.py             # Abstract LLM client interface (ILLMClient, LLMResponse)
│   │   ├── anthropic_client.py         # Anthropic Claude client
│   │   ├── gemini_client.py            # Native Google Gemini client
│   │   ├── openai_compatible_client.py # OpenAI-compatible client (OpenAI, OpenRouter, Ollama, LM Studio)
│   │   ├── langfuse_llm_client.py      # Optional Langfuse tracing wrapper
│   │   └── tool_schema_builder.py      # Provider-specific tool schema conversion
│   ├── mcp_client/
│   │   ├── mcp_manager.py              # MCP server connection manager (MCPManager)
│   │   └── mcp_tool.py                 # Adapter wrapping MCP tools as ITool instances (MCPTool)
│   ├── memory/
│   │   ├── long_term_memory.py         # SQLite + FTS5 persistent memory storage
│   │   └── short_term_memory.py        # Token-aware context window management with auto-summarization
│   ├── message_logger/
│   │   ├── agent_event_subscriber.py   # Logging subscriber interface
│   │   ├── session_logger.py           # Per-session `.log` and `.jsonl` event logger
│   │   └── message_logger_service.py   # Raw LLM message logger for debugging
│   └── tool_framework/
│       ├── i_tool.py                   # Tool interface (ITool, ToolParameter, ToolResult)
│       └── tool_collection.py          # Tool registry (ToolCollection)
├── tools/
│   ├── fs_utils.py                     # Safe path resolution utility (prevents path traversal)
│   ├── calculator_tool.py              # Calculator tool
│   ├── current_date.py                 # Current date retrieval tool
│   ├── send_email_tool.py              # Gmail SMTP email tool
│   ├── read_email_tool.py              # Gmail IMAP email reader (async)
│   ├── download_attachments_tool.py    # Email attachment downloader (async)
│   ├── google_calendar_tool.py         # Google Calendar read tool
│   ├── create_calendar_event_tool.py   # Google Calendar event creation tool
│   ├── edit_calendar_event_tool.py     # Google Calendar event editing tool
│   ├── wiki_search_tool.py             # Fandom wiki search tool (MediaWiki API)
│   ├── wiki_page_tool.py               # Fandom wiki article reader
│   ├── tavily_search_tool.py           # Tavily web search tool
│   ├── tavily_extract_tool.py          # Tavily web extract tool
│   ├── recall_memory_tool.py           # Long-term memory recall tool
│   ├── save_memory_tool.py             # Long-term memory save tool
│   ├── read_file_tool.py               # File reading tool (with line offset/limit)
│   ├── write_file_tool.py              # File writing tool (auto-creates directories)
│   ├── edit_file_tool.py               # Targeted file editing tool (exact string replacement)
│   └── list_directory_tool.py          # Directory listing tool
├── streamlit_ui/
│   ├── app.py                          # Streamlit web UI entry point
│   ├── sidebar.py                      # Agent configuration sidebar (client, model, tools, MCP)
│   ├── chat_input.py                   # Chat input with multimodal support (image upload)
│   ├── chat_view.py                    # Chat history display
│   ├── event_log.py                    # Agent event visualization
│   ├── settings.py                     # Configuration UI
│   ├── client_factory.py               # LLM client instantiation
│   └── constants.py                    # Tool registry organized by category
├── mcp_servers/
│   ├── weather_server.py               # Weather MCP server (Open-Meteo API)
│   ├── fetch_url_server.py             # URL/HTML/Markdown fetcher MCP server
│   ├── packages_server.py              # Package tracking MCP server
│   ├── calculator_server.py            # Calculator MCP server
│   ├── analyze_image_server.py         # Vision analysis MCP server backed by Gemini
│   ├── oko_readonly_server.py          # Read-only OKO incident/task/notes MCP server
│   ├── send_aidevs_server.py           # AI Devs answer submission MCP server
│   ├── e2b_server.py                   # Isolated code execution sandbox via E2B
│   └── sleep_server.py                 # Utility wait/sleep MCP server
├── log_viewer/
│   ├── server.py                       # FastAPI dashboard backend
│   ├── runner.py                       # AI Devs exercise process runner
│   ├── parser.py                       # Log line classification helpers
│   ├── tail.py                         # File/process streaming utilities
│   └── templates/viewer.html           # Dashboard UI
├── ai_devs_4/                          # Task-specific experiments, prompts, tools, and MCP configs
├── app.py                              # CLI/demo entry point
├── streamlit_app.py                    # Thin wrapper around `streamlit_ui.app`
├── mcp_config.json                     # Default MCP server configuration
├── run_log_viewer.sh                   # Starts the FastAPI log viewer/dashboard
├── pyproject.toml                      # Package metadata and setuptools config
├── pyrightconfig.json                  # Type-checker configuration
└── requirements.txt                    # Runtime dependencies
```

## Tech Stack

- **Python 3.11+**
- **anthropic** (`>=0.18.0`) — Anthropic Claude API
- **openai** (`>=2.0.0`) — OpenAI-compatible API client
- **google-genai** (`>=1.0.0`) — Google Gemini API client
- **langfuse** — optional tracing/observability wrapper
- **mcp** (`>=1.0.0`) — Model Context Protocol client
- **httpx** — HTTP client for OpenAI-compatible APIs and web integrations
- **streamlit** — Web chat interface
- **python-dotenv** — Environment variable management
- **pydantic** — Data validation
- **tiktoken** — token accounting for short-term memory management
- **cryptography** — Secure configuration encryption
- **fastapi**, **uvicorn** — MCP servers and log viewer backend
- **opencv-python**, **numpy** — vision helpers used in selected tasks and utilities
- **google-api-python-client**, **google-auth-httplib2**, **google-auth-oauthlib** — Google API integration

## Architecture

### ReAct Loop

The core loop in `SimpleAgent.run()`:

```
User Query → Plan → [Think → Act (tool call) → Observe → Update Plan] × N → Final Answer
```

1. Agent receives a user query
2. **(Planning)** LLM creates an initial step-by-step plan (3–7 steps) without calling any tools
3. LLM reasons and decides to call a tool (`stop_reason="tool_use"`) or provide a final answer (`stop_reason="end_turn"`)
4. If tool call — execute the tool, update the plan (marking steps as done/skipped), add result to conversation, go to step 3
5. If text response — return as final answer

Planning can be disabled via `AgentConfig(enable_planning=False)`.

### Planning System

Before entering the main loop the agent calls `_create_initial_plan()`, which asks the LLM to decompose the goal into numbered steps. The result is stored as an `AgentPlan` object.

After each tool execution, `_update_plan()` asks the LLM to review the steps taken and mark progress. The current plan is injected into the system prompt via `_build_system_prompt_with_plan()` so the agent stays aligned with the original strategy.

**Data structures** (`src/agent/simple_agent/agent_plan.py`):

```python
class PlanStepStatus(Enum):
    PENDING    = "pending"      # [ ] not started
    IN_PROGRESS = "in_progress" # [→] currently active
    COMPLETED  = "completed"    # [✓] done
    SKIPPED    = "skipped"      # [–] skipped

@dataclass
class PlanStep:
    step_number: int
    description: str
    status: PlanStepStatus
    notes: str | None = None

@dataclass
class AgentPlan:
    goal: str
    steps: list[PlanStep]
    created_at: datetime
    last_updated_at: datetime
```

The plan is accessible via `agent.plan` after a run and emits `PLAN_CREATED` / `PLAN_UPDATED` events.

### Self-Reflection

Every `reflection_interval` iterations, the agent evaluates its own progress. The LLM receives the last 5 actions and responds with one of:

- **CONTINUE** — making progress, keep going
- **FINISH** — enough information gathered, generate final answer
- **PIVOT** — current approach is weak, adjust the strategy and continue
- **STUCK** — not making progress, stop and report to user

### Memory System

The agent integrates a dual memory architecture:

- **Short-Term Memory**: Manages the immediate conversation context window.
- **Long-Term Memory**: Provides persistent information storage across sessions, accessible via `save_memory_tool` and `recall_memory_tool`.

Short-term memory is **token-aware** — it tracks actual token usage from LLM responses and automatically summarizes older messages when the context window fills up. Long-term memory is persisted in SQLite and uses FTS5 for recall/search. Key settings in `ShortTermMemoryConfig`: `summarization_threshold` (default 80%), `min_recent_messages` (4), `response_token_reserve` (4096).

### MCP Integration (Model Context Protocol)

The agent can connect to external **MCP servers** to dynamically discover and use tools at runtime. This is handled by `MCPManager` in `src/mcp_client/`.

**How it works:**

1. `MCPManager` reads server definitions from `mcp_config.json`
2. Connects to each server via stdio transport
3. Discovers available tools and wraps them as `ITool` instances (`MCPTool` adapter)
4. Tool names are prefixed with the server name, e.g. `weather__check_weather`

`MCPManager` supports the async context manager protocol:

```python
async with MCPManager("mcp_config.json") as mcp:
    mcp_tools = mcp.tools  # list[ITool]
```

**Configuration** (`mcp_config.json`):

```json
{
  "mcpServers": {
    "packages": {
      "command": "python",
      "args": ["mcp_servers/packages_server.py"]
    },
    "weather": {
      "command": "python",
      "args": ["mcp_servers/weather_server.py"]
    }
  }
}
```

Each server entry specifies a `command`, `args`, and optional `env` dict. The repository ships with more MCP servers than the default config enables.

### Agent Status

```python
class AgentStatus(Enum):
    RUNNING = "running"            # Agent is executing
    FINISHED = "finished"          # Final answer provided
    MAX_ITERATIONS = "max_iterations"  # Iteration limit reached
    STUCK = "stuck"                # Self-reflection detected no progress
    ERROR = "error"                # Exception occurred
```

### Agent Configuration

```python
@dataclass
class AgentConfig:
    max_iterations: int = 10           # Max Think-Act-Observe cycles
    reflection_interval: int = 3       # Self-reflect every N iterations
    enable_self_reflection: bool = True
    enable_planning: bool = True       # Create and track a step-by-step plan
    max_tokens: int = 4096             # Max tokens for a single LLM response
    agent_name: str | None = None      # Optional name used in events/logs
    session_id: str | None = None      # Optional tracing/session identifier
```

### Event System

All agent actions are logged as `AgentEvent` objects with types such as `USER_MESSAGE`, `ASSISTANT_MESSAGE`, `LLM_RESPONSE`, `TOOL_CALL`, `TOOL_RESULT`, `SELF_REFLECTION`, `REASONING`, `PLAN_CREATED`, `PLAN_UPDATED`, `STATUS_CHANGE`, and `ERROR`. Events are accessible via `agent.event_log` after a run.

### Message Logging (Debugging)

`MessageLoggerService` (in `src/message_logger/`) logs raw LLM messages (user, assistant, tool calls, tool results) as JSON to `agent_messages.log`. For richer per-run inspection, `SessionLogger` can also write paired `.log` and `.jsonl` files that are viewable through the bundled log viewer dashboard.

### LLM Clients

All clients implement `ILLMClient.chat()` and return a unified `LLMResponse`. Tool schemas are automatically converted from `ITool` to the provider's format.

| Client                     | Provider                              | Default model              |
| -------------------------- | ------------------------------------- | -------------------------- |
| `AnthropicClient`          | Anthropic Claude                      | `claude-sonnet-4-20250514` |
| `GeminiClient`             | Google Gemini                         | `gemini-3-flash-preview`   |
| `OpenAICompatibleClient`   | OpenAI, OpenRouter, Ollama, LM Studio | `llama3.1`                 |
| `LangfuseTrackedLLMClient` | Wrapper around any `ILLMClient`       | Inherits wrapped client    |

## Creating New Tools

### Interface Reference

```python
# src/tool_framework/i_tool.py

@dataclass
class ToolParameter:
    name: str           # Parameter name (used as key in args dict)
    type: str           # JSON Schema type: "string", "integer", "float", "boolean", "list", "dict"
    required: bool      # If True, agent must provide this parameter
    default: any        # Default value (use None if no default)
    description: str    # Description shown to the LLM — be specific, include examples and format

@dataclass
class ToolResult:
    tool_name: str      # Name of the tool that was executed
    parameters: dict    # Parameters that were passed
    result: str         # Result string — the LLM sees this as the tool's output
    is_error: bool      # If True, signals the agent that the tool call failed

class ITool(ABC):
    def __init__(self, name: str, description: str, parameters: list[ToolParameter]):
        self.name = name
        self.description = description
        self.parameters = parameters

    @abstractmethod
    async def run(self, args: dict[str, any]) -> ToolResult:
        """Execute the tool. Must return a ToolResult."""
        pass

    def validate_parameters(self, args: dict[str, any]) -> None:
        """Validates args against declared parameters. Raises ValueError on failure."""
        pass
```

### Step-by-step

1. Create a new file in `tools/` (e.g. `tools/weather_tool.py`)
2. Import the base classes from `tool_framework.i_tool`
3. Create a class inheriting from `ITool`
4. In `__init__`, define `name`, `description`, and `parameters`
5. Implement `run(self, args) -> ToolResult`
6. Call `self.validate_parameters(args)` at the start of `run()`
7. Return `ToolResult` — on errors, return a `ToolResult` with `result="Error: <message>"` (don't raise exceptions)
8. Register the tool in a `ToolCollection` in your entry point

### Conventions

- **Tool name**: lowercase, snake_case (e.g. `"get_weather"`)
- **Tool description**: concise sentence explaining what the tool does and when to use it — this is what the LLM reads to decide whether to call it
- **Parameter descriptions**: include expected format and examples (e.g. `"City name, e.g. 'Warsaw'"`)
- **Parameter types**: use JSON Schema types — `"string"`, `"integer"`, `"number"`, `"boolean"`, `"array"`, `"object"`
- **Error handling**: always return a `ToolResult` with `result="Error: ..."` instead of raising exceptions — this lets the agent recover and retry
- **Environment variables**: for secrets/config, use `os.getenv()` inside `run()` and document required env vars

### Complete Example

```python
# tools/weather_tool.py

import os
import httpx
from tool_framework.i_tool import ITool, ToolResult, ToolParameter


class WeatherTool(ITool):
    """Fetches current weather for a given city."""

    def __init__(self):
        super().__init__(
            name="get_weather",
            description="Get current weather for a city. Use this when the user asks about weather conditions.",
            parameters=[
                ToolParameter(
                    name="city",
                    type="string",
                    required=True,
                    default=None,
                    description="City name, e.g. 'Warsaw', 'New York'",
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)
        city = args["city"]
        api_key = os.getenv("WEATHER_API_KEY")

        if not api_key:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: WEATHER_API_KEY environment variable is not set.",
            )

        try:
            response = httpx.get(
                "https://api.weatherapi.com/v1/current.json",
                params={"key": api_key, "q": city},
            )
            response.raise_for_status()
            data = response.json()
            current = data["current"]
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Weather in {city}: {current['condition']['text']}, {current['temp_c']}°C, humidity {current['humidity']}%",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to fetch weather — {str(e)}",
            )
```

### Registering the Tool

```python
# In app.py or streamlit_app.py
from tool_framework.tool_collection import ToolCollection
from tools.weather_tool import WeatherTool

tools = ToolCollection([WeatherTool()])
agent = SimpleAgent(tool_collection=tools, llm_client=client)
```

## Configuration

The application uses a secure `ConfigService` to manage API keys and credentials, accessible directly through the Streamlit Settings UI. Core settings are stored in an encrypted SQLite database after you set a master password.

You can also initially set these via environment variables (`.env`), and the configuration service will read them.

| Variable                          | Required             | Description                          |
| --------------------------------- | -------------------- | ------------------------------------ |
| `ANTHROPIC_API_KEY`               | For Anthropic client | Anthropic API key                    |
| `OPEN_AI_API_KEY`                 | For OpenAI client    | OpenAI API key                       |
| `TAVILY_API_KEY`                  | For Tavily tools     | Tavily search API key                |
| `EMAIL_TO`                        | For email tool       | Recipient email address              |
| `EMAIL_FROM`                      | For email tool       | Sender Gmail address                 |
| `EMAIL_APP_PASSWORD`              | For email tool       | Gmail app password                   |
| `ATTACHMENTS_DIR`                 | For email tool       | Directory for downloaded attachments |
| `GOOGLE_SERVICE_ACCOUNT_KEY_PATH` | For calendar tool    | Path to Google service account JSON  |
| `GOOGLE_CALENDAR_ID`              | For calendar tool    | Google Calendar ID                   |
| `FILESYSTEM_BASE_DIR`             | For file tools       | Root directory exposed to file tools |

_Note: In the Web UI, the Google Service Account Key can be uploaded or pasted directly as JSON._

Some optional modules and examples also read environment variables directly, including `GEMINI_API_KEY`, `OPEN_ROUTER_API_KEY`, `AI_DEVS_API_KEY`, `OKO_BASE_URL`, and `OKO_PASSWORD`.

### Setup

```bash
pip install -r requirements.txt
# optionally create/update `.env` with the variables above
```

## Running

```bash
# Web UI
streamlit run streamlit_app.py
```
