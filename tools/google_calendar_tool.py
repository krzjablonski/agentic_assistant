import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from config_service import config_service


class GoogleCalendarTool(ITool):
    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

    def __init__(self):
        super().__init__(
            name="google_calendar",
            description="Get calendar 10 events from given date",
            parameters=[
                ToolParameter(
                    name="date",
                    type="string",
                    required=True,
                    default=datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                    description="Date in ISO format (e.g., '2026-02-12T00:00:00Z')",
                )
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        service_account_path = config_service.get("calendar.service_account_key_path")
        calendar_id = config_service.get("calendar.calendar_id")

        if not service_account_path:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: Service Account Key Path is not configured. Check Settings.",
            )
        if not calendar_id:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: Google Calendar ID is not configured. Check Settings.",
            )

        try:
            creds = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=self.SCOPES,
            )
            service = build("calendar", "v3", credentials=creds)

            events_result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=args["date"],
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            if not events:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result="No upcoming events found.",
                )

            events_str = ""
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                events_str += f"{start} {event['summary']}\n"

            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=events_str,
            )

        except HttpError as error:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: {error}",
            )
