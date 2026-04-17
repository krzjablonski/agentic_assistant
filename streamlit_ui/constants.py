from agent.agent_event import AgentEventType
from tools.send_email_tool import SendEmailTool
from tools.read_email_tool import ReadEmailTool
from tools.download_attachments_tool import DownloadAttachmentsTool
from tools.google_calendar_tool import GoogleCalendarTool
from tools.create_calendar_event_tool import CreateCalendarEventTool
from tools.edit_calendar_event_tool import EditCalendarEventTool
from tools.wiki_search_tool import WikiSearchTool
from tools.wiki_page_tool import WikiPageTool
from tools.current_date import CurrentDateTool
from tools.save_memory_tool import SaveMemoryTool
from tools.recall_memory_tool import RecallMemoryTool
from tools.tavily_search_tool import TavilySearchTool
from tools.tavily_extract_tool import TavilyExtractTool
from tools.read_file_tool import ReadFileTool
from tools.write_file_tool import WriteFileTool
from tools.list_directory_tool import ListDirectoryTool
from tools.edit_file_tool import EditFileTool

TOOL_REGISTRY: dict[str, list[tuple[str, type]]] = {
    "Email": [
        ("Send Email", SendEmailTool),
        ("Read Email", ReadEmailTool),
        ("Download Attachments", DownloadAttachmentsTool),
    ],
    "Calendar": [
        ("Google Calendar", GoogleCalendarTool),
        ("Create Calendar Event", CreateCalendarEventTool),
        ("Edit Calendar Event", EditCalendarEventTool),
    ],
    "Wiki": [
        ("Search Wiki", WikiSearchTool),
        ("Get Wiki Page", WikiPageTool),
    ],
    "Web Search": [
        ("Search Web (Tavily)", TavilySearchTool),
        ("Extract Webpage (Tavily)", TavilyExtractTool),
    ],
    "File System": [
        ("Read File", ReadFileTool),
        ("Write File", WriteFileTool),
        ("List Directory", ListDirectoryTool),
        ("Edit File", EditFileTool),
    ],
    "Utility": [
        ("Current Date", CurrentDateTool),
    ],
    "Memory": [
        ("Save Memory", SaveMemoryTool),
        ("Recall Memory", RecallMemoryTool),
    ],
}

MEMORY_TOOL_CLASSES = {SaveMemoryTool, RecallMemoryTool}

_EVENT_ICONS = {
    AgentEventType.USER_MESSAGE: "\U0001f4ac",
    AgentEventType.ASSISTANT_MESSAGE: "\U0001f5e3",
    AgentEventType.LLM_RESPONSE: "\U0001f916",
    AgentEventType.TOOL_CALL: "\U0001f527",
    AgentEventType.TOOL_RESULT: "\U0001f4cb",
    AgentEventType.SELF_REFLECTION: "\U0001fa9e",
    AgentEventType.STATUS_CHANGE: "\U0001f504",
    AgentEventType.ERROR: "\u274c",
    AgentEventType.REASONING: "\U0001f9e0",
    AgentEventType.PLAN_CREATED: "\U0001f5fa",
    AgentEventType.PLAN_UPDATED: "\U0001f4dd",
}
