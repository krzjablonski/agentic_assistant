import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from config_service import config_service


class CreateCalendarEventTool(ITool):
    SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

    def __init__(self):
        super().__init__(
            name="create_calendar_event",
            description=(
                "Create a new event on Google Calendar (timed or all-day). "
                "Use this when the user wants to schedule, add, or book an event. "
                "For timed events, provide start_datetime and end_datetime. "
                "For all-day events, provide start_date and end_date instead."
            ),
            parameters=[
                ToolParameter(
                    name="summary",
                    type="string",
                    required=True,
                    default=None,
                    description="Event title (e.g., 'Team standup')",
                ),
                ToolParameter(
                    name="start_datetime",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "Start time for timed events in ISO 8601 format "
                        "(e.g., '2026-03-01T14:00:00Z' or '2026-03-01T14:00:00+02:00'). "
                        "Required for timed events. Do not use with start_date/end_date."
                    ),
                ),
                ToolParameter(
                    name="end_datetime",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "End time for timed events in ISO 8601 format "
                        "(e.g., '2026-03-01T15:00:00Z' or '2026-03-01T15:00:00+02:00'). "
                        "Required for timed events. Do not use with start_date/end_date."
                    ),
                ),
                ToolParameter(
                    name="start_date",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "Start date for all-day events in YYYY-MM-DD format "
                        "(e.g., '2026-03-01'). "
                        "Required for all-day events. Do not use with start_datetime/end_datetime."
                    ),
                ),
                ToolParameter(
                    name="end_date",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "End date (exclusive) for all-day events in YYYY-MM-DD format "
                        "(e.g., '2026-03-02' for a single-day event on March 1st). "
                        "Required for all-day events. Do not use with start_datetime/end_datetime."
                    ),
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    required=False,
                    default=None,
                    description="Optional event description or notes",
                ),
                ToolParameter(
                    name="location",
                    type="string",
                    required=False,
                    default=None,
                    description="Optional event location (e.g., 'Conference Room B' or a URL)",
                ),
                ToolParameter(
                    name="timezone",
                    type="string",
                    required=False,
                    default="UTC",
                    description=(
                        "IANA timezone name used when start_datetime/end_datetime lack a UTC offset. "
                        "Ignored for all-day events and if datetimes already include an offset. "
                        "Examples: 'Europe/Warsaw', 'America/New_York', 'UTC'"
                    ),
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)

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

        summary = args["summary"]
        start_datetime_str = args.get("start_datetime")
        end_datetime_str = args.get("end_datetime")
        start_date_str = args.get("start_date")
        end_date_str = args.get("end_date")
        description = args.get("description")
        location = args.get("location")
        timezone = args.get("timezone", "UTC")

        has_datetime = start_datetime_str is not None or end_datetime_str is not None
        has_date = start_date_str is not None or end_date_str is not None

        if has_datetime and has_date:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: Provide either start_datetime/end_datetime (timed event) or start_date/end_date (all-day event), not both.",
            )

        if not has_datetime and not has_date:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: Provide start_datetime and end_datetime for a timed event, or start_date and end_date for an all-day event.",
            )

        if has_datetime and (start_datetime_str is None or end_datetime_str is None):
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: start_datetime and end_datetime must be provided together.",
            )

        if has_date and (start_date_str is None or end_date_str is None):
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: start_date and end_date must be provided together.",
            )

        if has_datetime:
            try:
                start_dt = datetime.datetime.fromisoformat(start_datetime_str)
                end_dt = datetime.datetime.fromisoformat(end_datetime_str)
            except ValueError as e:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"Error: Could not parse datetime - {str(e)}. Use ISO 8601 format, e.g. '2026-03-01T14:00:00Z'.",
                )

            if end_dt <= start_dt:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result="Error: end_datetime must be after start_datetime.",
                )

            def build_time_field(dt: datetime.datetime) -> dict:
                if dt.tzinfo is not None:
                    return {"dateTime": dt.isoformat()}
                return {"dateTime": dt.isoformat(), "timeZone": timezone}

            event_body = {
                "summary": summary,
                "start": build_time_field(start_dt),
                "end": build_time_field(end_dt),
            }
        else:
            try:
                start_d = datetime.date.fromisoformat(start_date_str)
                end_d = datetime.date.fromisoformat(end_date_str)
            except ValueError as e:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"Error: Could not parse date - {str(e)}. Use YYYY-MM-DD format, e.g. '2026-03-01'.",
                )

            if end_d <= start_d:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result="Error: end_date must be after start_date.",
                )

            event_body = {
                "summary": summary,
                "start": {"date": start_d.isoformat()},
                "end": {"date": end_d.isoformat()},
            }

        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        try:
            creds = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=self.SCOPES,
            )
            service = build("calendar", "v3", credentials=creds)

            event = (
                service.events()
                .insert(calendarId=calendar_id, body=event_body)
                .execute()
            )

            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=(
                    f"Event created successfully. "
                    f"ID: {event['id']}. "
                    f"Link: {event.get('htmlLink', 'N/A')}"
                ),
            )

        except HttpError as error:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: {error}",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to create calendar event - {str(e)}",
            )
