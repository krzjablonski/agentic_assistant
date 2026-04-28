import imaplib
import re
import time
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from config_service import config_service


class CreateDraftEmailTool(ITool):
    IMAP_SERVER = "imap.gmail.com"
    IMAP_PORT = 993
    DRAFTS_FOLDER = '"[Gmail]/Drafts"'
    FALLBACK_DRAFTS_FOLDERS = (
        DRAFTS_FOLDER,
        '"[Google Mail]/Drafts"',
        '"Drafts"',
        "Drafts",
    )

    def __init__(self):
        super().__init__(
            name="create_draft_email",
            description=(
                "Create a Gmail draft (does NOT send). "
                "The user will review and send it by hand."
            ),
            parameters=[
                ToolParameter(
                    name="to",
                    type="string",
                    required=False,
                    description=(
                        "Draft recipient address. If omitted, falls back to the "
                        "configured default recipient."
                    ),
                    default="",
                ),
                ToolParameter(
                    name="subject",
                    type="string",
                    required=True,
                    description="Email subject",
                    default="",
                ),
                ToolParameter(
                    name="body",
                    type="string",
                    required=True,
                    description="Email body",
                    default="",
                ),
            ],
        )

    async def run(self, parameters: dict) -> ToolResult:
        """Create a Gmail draft via IMAP APPEND to [Gmail]/Drafts."""
        self.validate_parameters(parameters)

        to = parameters.get("to") or config_service.get("email.to")
        sender = config_service.get("email.from")
        app_password = config_service.get("email.app_password")
        subject = parameters["subject"]
        body = parameters["body"]

        if not to:
            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result="Error: Draft recipient is missing. Provide `to` or configure Default Recipient in Settings.",
            )

        if not sender or not app_password:
            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result="Error: Gmail Address and Gmail App Password are not configured. Check Settings.",
            )

        try:
            message = MIMEText(body)
            message["To"] = to
            message["From"] = sender
            message["Subject"] = subject
            message["Date"] = formatdate(localtime=True)
            message["Message-ID"] = make_msgid()

            mail = imaplib.IMAP4_SSL(self.IMAP_SERVER, self.IMAP_PORT)

            try:
                mail.login(sender, app_password)
            except imaplib.IMAP4.error:
                return ToolResult(
                    tool_name=self.name,
                    parameters={"to": to, "subject": subject, "body": body},
                    result="Error: IMAP authentication failed. Check EMAIL_FROM and EMAIL_APP_PASSWORD.",
                )

            drafts_folder = self._find_drafts_folder(mail)

            try:
                status, response = self._append_to_drafts(mail, drafts_folder, message)
            finally:
                mail.logout()

            if status != "OK":
                return ToolResult(
                    tool_name=self.name,
                    parameters={"to": to, "subject": subject, "body": body},
                    result=f"Error: Failed to create draft - IMAP APPEND returned {status}: {response!r}",
                )

            return ToolResult(
                tool_name=self.name,
                parameters={"to": to, "subject": subject, "body": body},
                result=f"Draft created successfully for {to}. Open Gmail > Drafts to review and send.",
            )

        except imaplib.IMAP4.error as e:
            return ToolResult(
                tool_name=self.name,
                parameters={"to": to, "subject": subject, "body": body},
                result=f"Error: IMAP error - {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters={"to": to, "subject": subject, "body": body},
                result=f"Error: Failed to create draft - {str(e)}",
            )

    def _append_to_drafts(
        self,
        mail: imaplib.IMAP4_SSL,
        drafts_folder: str | None,
        message: MIMEText,
    ) -> tuple[str, list[bytes] | list[str] | None]:
        folders = []
        if drafts_folder:
            folders.append(drafts_folder)
        folders.extend(
            folder
            for folder in self.FALLBACK_DRAFTS_FOLDERS
            if folder not in folders
        )

        last_status = "NO"
        last_response = None
        for folder in folders:
            status, response = mail.append(
                folder,
                "\\Draft",
                imaplib.Time2Internaldate(time.time()),
                message.as_bytes(),
            )
            if status == "OK":
                return status, response
            last_status = status
            last_response = response

            if not self._is_missing_folder_response(response):
                break

        return last_status, last_response

    def _find_drafts_folder(self, mail: imaplib.IMAP4_SSL) -> str | None:
        status, mailboxes = mail.list()
        if status != "OK" or not mailboxes:
            return None

        for mailbox in mailboxes:
            if not mailbox:
                continue
            mailbox_text = (
                mailbox.decode("utf-8", errors="replace")
                if isinstance(mailbox, bytes)
                else str(mailbox)
            )
            parsed = self._parse_list_mailbox(mailbox_text)
            if parsed and "\\Drafts" in parsed["flags"]:
                return self._quote_mailbox(parsed["name"])

        return None

    def _parse_list_mailbox(self, mailbox_text: str) -> dict[str, str] | None:
        match = re.match(
            r"\((?P<flags>.*?)\)\s+\"(?:\\.|[^\"])*\"\s+(?P<name>.+)$",
            mailbox_text,
        )
        if not match:
            return None

        name_token = match.group("name").strip()
        return {
            "flags": match.group("flags"),
            "name": self._unquote_mailbox(name_token),
        }

    def _unquote_mailbox(self, name_token: str) -> str:
        if len(name_token) < 2 or not name_token.startswith('"'):
            return name_token

        chars = []
        escaped = False
        for char in name_token[1:]:
            if escaped:
                chars.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                break
            else:
                chars.append(char)

        return "".join(chars)

    def _quote_mailbox(self, mailbox: str) -> str:
        if mailbox.upper() == "INBOX" or (
            len(mailbox) >= 2 and mailbox.startswith('"') and mailbox.endswith('"')
        ):
            return mailbox

        escaped = mailbox.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _is_missing_folder_response(
        self, response: list[bytes] | list[str] | None
    ) -> bool:
        response_text = " ".join(
            item.decode("utf-8", errors="replace")
            if isinstance(item, bytes)
            else str(item)
            for item in response or []
        )
        return "[TRYCREATE]" in response_text or "Folder doesn't exist" in response_text
