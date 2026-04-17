import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from config_service import config_service


class EditCalendarEventTool(ITool):
    SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

    def __init__(self):
        super().__init__(
            name="edit_calendar_event",
            description=(
                "Edit an existing Google Calendar event (timed or all-day). "
                "Use this when the user wants to update, reschedule, or modify an event. "
                "Requires the event ID. Only provided fields will be updated. "
                "To reschedule a timed event, provide start_datetime and end_datetime. "
                "To change to or update an all-day event, provide start_date and end_date."
            ),
            parameters=[
                ToolParameter(
                    name="event_id",
                    type="string",
                    required=True,
                    default=None,
                    description="The ID of the event to edit (returned by create_calendar_event or google_calendar tools)",
                ),
                ToolParameter(
                    name="summary",
                    type="string",
                    required=False,
                    default=None,
                    description="New event title",
                ),
                ToolParameter(
                    name="start_datetime",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "New start time in ISO 8601 format "
                        "(e.g., '2026-03-01T14:00:00Z' or '2026-03-01T14:00:00+02:00'). "
                        "Must be provided together with end_datetime. "
                        "Do not use with start_date/end_date."
                    ),
                ),
                ToolParameter(
                    name="end_datetime",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "New end time in ISO 8601 format "
                        "(e.g., '2026-03-01T15:00:00Z' or '2026-03-01T15:00:00+02:00'). "
                        "Must be provided together with start_datetime. "
                        "Do not use with start_date/end_date."
                    ),
                ),
                ToolParameter(
                    name="start_date",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "New start date for all-day events in YYYY-MM-DD format "
                        "(e.g., '2026-03-01'). Must be provided together with end_date. "
                        "Do not use with start_datetime/end_datetime."
                    ),
                ),
                ToolParameter(
                    name="end_date",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "New end date (exclusive) for all-day events in YYYY-MM-DD format "
                        "(e.g., '2026-03-02' for a single-day event on March 1st). "
                        "Must be provided together with start_date. "
                        "Do not use with start_datetime/end_datetime."
                    ),
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    required=False,
                    default=None,
                    description="New event description or notes",
                ),
                ToolParameter(
                    name="location",
                    type="string",
                    required=False,
                    default=None,
                    description="New event location (e.g., 'Conference Room B' or a URL)",
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

        event_id = args["event_id"]
        summary = args.get("summary")
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

        patch_body = {}

        if summary is not None:
            patch_body["summary"] = summary

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

            patch_body["start"] = build_time_field(start_dt)
            patch_body["end"] = build_time_field(end_dt)

        elif has_date:
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

            patch_body["start"] = {"date": start_d.isoformat()}
            patch_body["end"] = {"date": end_d.isoformat()}

        if description is not None:
            patch_body["description"] = description
        if location is not None:
            patch_body["location"] = location

        if not patch_body:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: No fields to update. Provide at least one field to change.",
            )

        try:
            creds = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=self.SCOPES,
            )
            service = build("calendar", "v3", credentials=creds)

            event = (
                service.events()
                .patch(calendarId=calendar_id, eventId=event_id, body=patch_body)
                .execute()
            )

            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=(
                    f"Event updated successfully. "
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
                result=f"Error: Failed to update calendar event - {str(e)}",
            )
