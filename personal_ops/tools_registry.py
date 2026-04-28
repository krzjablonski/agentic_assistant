from dataclasses import dataclass

from tools.create_calendar_event_tool import CreateCalendarEventTool
from tools.create_draft_email_tool import CreateDraftEmailTool
from tools.current_date import CurrentDateTool
from tools.download_attachments_tool import DownloadAttachmentsTool
from tools.edit_calendar_event_tool import EditCalendarEventTool
from tools.edit_file_tool import EditFileTool
from tools.google_calendar_tool import GoogleCalendarTool
from tools.list_directory_tool import ListDirectoryTool
from tools.read_email_tool import ReadEmailTool
from tools.read_file_tool import ReadFileTool
from tools.recall_memory_tool import RecallMemoryTool
from tools.save_memory_tool import SaveMemoryTool
from tools.send_email_tool import SendEmailTool
from tools.tavily_extract_tool import TavilyExtractTool
from tools.tavily_search_tool import TavilySearchTool
from tools.wiki_page_tool import WikiPageTool
from tools.wiki_search_tool import WikiSearchTool
from tools.write_file_tool import WriteFileTool


@dataclass(frozen=True)
class ToolDefinition:
    tool_name: str
    label: str
    tool_class: type


TOOL_REGISTRY: dict[str, list[ToolDefinition]] = {
    "Email": [
        ToolDefinition("send_email", "Send Email", SendEmailTool),
        ToolDefinition(
            "create_draft_email",
            "Create Draft Email",
            CreateDraftEmailTool,
        ),
        ToolDefinition("read_email", "Read Email", ReadEmailTool),
        ToolDefinition(
            "download_attachments",
            "Download Attachments",
            DownloadAttachmentsTool,
        ),
    ],
    "Calendar": [
        ToolDefinition("google_calendar", "Google Calendar", GoogleCalendarTool),
        ToolDefinition(
            "create_calendar_event",
            "Create Calendar Event",
            CreateCalendarEventTool,
        ),
        ToolDefinition("edit_calendar_event", "Edit Calendar Event", EditCalendarEventTool),
    ],
    "Wiki": [
        ToolDefinition("wiki_search", "Search Wiki", WikiSearchTool),
        ToolDefinition("wiki_page", "Get Wiki Page", WikiPageTool),
    ],
    "Web Search": [
        ToolDefinition("tavily_search", "Search Web (Tavily)", TavilySearchTool),
        ToolDefinition(
            "tavily_extract",
            "Extract Webpage (Tavily)",
            TavilyExtractTool,
        ),
    ],
    "File System": [
        ToolDefinition("read_file", "Read File", ReadFileTool),
        ToolDefinition("write_file", "Write File", WriteFileTool),
        ToolDefinition("list_directory", "List Directory", ListDirectoryTool),
        ToolDefinition("edit_file", "Edit File", EditFileTool),
    ],
    "Utility": [
        ToolDefinition("current_date", "Current Date", CurrentDateTool),
    ],
    "Memory": [
        ToolDefinition("save_memory", "Save Memory", SaveMemoryTool),
        ToolDefinition("recall_memory", "Recall Memory", RecallMemoryTool),
    ],
}

TOOL_NAME_TO_CLASS = {
    tool.tool_name: tool.tool_class
    for tool_entries in TOOL_REGISTRY.values()
    for tool in tool_entries
}
TOOL_NAME_TO_DEFINITION = {
    tool.tool_name: tool
    for tool_entries in TOOL_REGISTRY.values()
    for tool in tool_entries
}

MEMORY_TOOL_NAMES = {"save_memory", "recall_memory"}
MEMORY_TOOL_CLASSES = {
    TOOL_NAME_TO_CLASS[tool_name] for tool_name in MEMORY_TOOL_NAMES
}
