import re
import imaplib
import email
from email.header import decode_header

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from config_service import config_service


class ReadEmailTool(ITool):
    IMAP_SERVER = "imap.gmail.com"
    IMAP_PORT = 993
    MAX_BODY_LENGTH = 500
    MAX_EMAILS = 1000

    def __init__(self):
        super().__init__(
            name="read_email",
            description=(
                "Read emails from a Gmail mailbox. "
                "Can search by criteria like UNSEEN, FROM, SUBJECT, SINCE. "
                "Returns email metadata and body text."
            ),
            parameters=[
                ToolParameter(
                    name="count",
                    type="integer",
                    required=False,
                    default=5,
                    description="Number of emails to retrieve (1-1000, default 5)",
                ),
                ToolParameter(
                    name="folder",
                    type="string",
                    required=False,
                    default="INBOX",
                    description=(
                        'IMAP folder to read from (default "INBOX"). '
                        'Examples: "INBOX", "[Gmail]/Sent Mail", "[Gmail]/Drafts"'
                    ),
                ),
                ToolParameter(
                    name="search_criteria",
                    type="string",
                    required=False,
                    default="ALL",
                    description=(
                        'IMAP search criteria (default "ALL"). '
                        'Examples: "UNSEEN", "FROM john@example.com", '
                        '"SUBJECT meeting", "SINCE 10-Feb-2026"'
                    ),
                ),
            ],
        )

    async def run(self, parameters: dict) -> ToolResult:
        """Read emails from Gmail via IMAP."""
        self.validate_parameters(parameters)

        count = parameters.get("count", 5)
        folder = parameters.get("folder", "INBOX")
        search_criteria = parameters.get("search_criteria", "ALL")

        count = max(1, min(count, self.MAX_EMAILS))

        user = config_service.get("email.from")
        app_password = config_service.get("email.app_password")

        if not user or not app_password:
            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result="Error: Gmail Address and Gmail App Password are not configured. Check Settings.",
            )

        try:
            mail = imaplib.IMAP4_SSL(self.IMAP_SERVER, self.IMAP_PORT)

            try:
                mail.login(user, app_password)
            except imaplib.IMAP4.error:
                return ToolResult(
                    tool_name=self.name,
                    parameters=parameters,
                    result="Error: IMAP authentication failed. Check EMAIL_FROM and EMAIL_APP_PASSWORD.",
                )

            status, _ = mail.select(folder, readonly=True)
            if status != "OK":
                mail.logout()
                return ToolResult(
                    tool_name=self.name,
                    parameters=parameters,
                    result=f"Error: Could not open folder '{folder}'.",
                )

            status, data = mail.uid("search", None, search_criteria)
            if status != "OK":
                mail.logout()
                return ToolResult(
                    tool_name=self.name,
                    parameters=parameters,
                    result=f"Error: Search failed for criteria '{search_criteria}'.",
                )

            message_uids = data[0].split()
            if not message_uids:
                mail.logout()
                return ToolResult(
                    tool_name=self.name,
                    parameters=parameters,
                    result=f"No emails found matching criteria '{search_criteria}' in {folder}.",
                )

            selected_uids = message_uids[-count:]
            selected_uids.reverse()

            emails = []
            for uid in selected_uids:
                status, msg_data = mail.uid("fetch", uid, "(RFC822)")
                if status == "OK":
                    raw_bytes = msg_data[0][1]
                    uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
                    parsed = self._parse_email(raw_bytes, uid_str)
                    emails.append(parsed)

            mail.logout()

            if not emails:
                return ToolResult(
                    tool_name=self.name,
                    parameters=parameters,
                    result="No emails could be retrieved.",
                )

            header = f'Found {len(emails)} email(s) matching criteria "{search_criteria}" in {folder}:\n'
            body_parts = []
            for i, em in enumerate(emails):
                body_parts.append(self._format_email(em, i + 1, len(emails)))

            result_text = header + "\n".join(body_parts) + "\n--- End of results ---"

            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result=result_text,
            )

        except imaplib.IMAP4.error as e:
            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result=f"Error: IMAP error - {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result=f"Error: Failed to read emails - {str(e)}",
            )

    def _parse_email(self, raw_bytes: bytes, uid: str) -> dict:
        msg = email.message_from_bytes(raw_bytes)
        return {
            "uid": uid,
            "from": self._decode_header_value(msg.get("From", "")),
            "to": self._decode_header_value(msg.get("To", "")),
            "date": msg.get("Date", ""),
            "subject": self._decode_header_value(msg.get("Subject", "(No Subject)")),
            "body": self._get_body(msg),
            "attachments": self._get_attachment_names(msg),
        }

    def _decode_header_value(self, header_value: str) -> str:
        parts = decode_header(header_value)
        decoded_parts = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded_parts.append(part)
        return " ".join(decoded_parts)

    def _get_body(self, msg: email.message.Message) -> str:
        if msg.is_multipart():
            text_part = None
            html_part = None
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in disposition:
                    continue
                if content_type == "text/plain" and text_part is None:
                    text_part = part
                elif content_type == "text/html" and html_part is None:
                    html_part = part
            target = text_part or html_part
            if target is None:
                return "[No readable content]"
        else:
            target = msg

        charset = target.get_content_charset() or "utf-8"
        payload = target.get_payload(decode=True)
        if payload is None:
            return "[No readable content]"

        text = payload.decode(charset, errors="replace")

        if target.get_content_type() == "text/html":
            text = self._strip_html(text)

        text = text.strip()
        if len(text) > self.MAX_BODY_LENGTH:
            text = (
                text[: self.MAX_BODY_LENGTH]
                + f"\n[Body truncated at {self.MAX_BODY_LENGTH} chars]"
            )
        return text

    def _strip_html(self, html: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _get_attachment_names(self, msg: email.message.Message) -> list[str]:
        names = []
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                filename = part.get_filename()
                if filename:
                    names.append(self._decode_header_value(filename))
        return names

    def _format_email(self, parsed: dict, index: int, total: int) -> str:
        lines = [f"--- Email {index}/{total} (UID: {parsed['uid']}) ---"]
        lines.append(f"From: {parsed['from']}")
        lines.append(f"To: {parsed['to']}")
        lines.append(f"Date: {parsed['date']}")
        lines.append(f"Subject: {parsed['subject']}")
        if parsed["attachments"]:
            lines.append(f"[Attachments: {', '.join(parsed['attachments'])}]")
        lines.append("")
        lines.append(parsed["body"])
        lines.append("")
        return "\n".join(lines)
