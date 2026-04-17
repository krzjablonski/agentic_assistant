import os
import re
import imaplib
import email
from email.header import decode_header

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from config_service import config_service


class DownloadAttachmentsTool(ITool):
    IMAP_SERVER = "imap.gmail.com"
    IMAP_PORT = 993

    def __init__(self):
        super().__init__(
            name="download_attachments",
            description=(
                "Download attachments from a specific email identified by its UID "
                "(from read_email results). Saves files to the configured directory."
            ),
            parameters=[
                ToolParameter(
                    name="message_uid",
                    type="string",
                    required=True,
                    default=None,
                    description=(
                        "IMAP UID of the email to download attachments from. "
                        "Get this from the read_email tool output (shown as 'UID: 12345')."
                    ),
                ),
                ToolParameter(
                    name="folder",
                    type="string",
                    required=False,
                    default="INBOX",
                    description=(
                        'IMAP folder (default "INBOX"). '
                        "Must match the folder used in read_email."
                    ),
                ),
            ],
        )

    async def run(self, parameters: dict) -> ToolResult:
        """Download attachments from a specific email via IMAP."""
        self.validate_parameters(parameters)

        message_uid = parameters["message_uid"]
        folder = parameters.get("folder", "INBOX")

        user = config_service.get("email.from")
        app_password = config_service.get("email.app_password")
        attachments_dir = config_service.get("email.attachments_dir")

        if not user or not app_password:
            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result="Error: Gmail Address and Gmail App Password are not configured. Check Settings.",
            )

        if not attachments_dir:
            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result="Error: Attachments Directory is not configured. Check Settings.",
            )

        os.makedirs(attachments_dir, exist_ok=True)

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

            status, msg_data = mail.uid('fetch', message_uid, '(RFC822)')
            if status != "OK" or not msg_data or msg_data[0] is None:
                mail.logout()
                return ToolResult(
                    tool_name=self.name,
                    parameters=parameters,
                    result=f"Error: No email found with UID '{message_uid}' in {folder}.",
                )

            raw_bytes = msg_data[0][1]
            mail.logout()

            msg = email.message_from_bytes(raw_bytes)

            saved_files = []
            for part in msg.walk():
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" not in disposition:
                    continue

                filename = part.get_filename()
                if not filename:
                    continue

                filename = self._decode_header_value(filename)
                filename = self._sanitize_filename(filename)

                if not filename:
                    filename = "attachment"

                filepath = self._unique_filepath(attachments_dir, filename)

                payload = part.get_payload(decode=True)
                if payload is None:
                    continue

                try:
                    with open(filepath, "wb") as f:
                        f.write(payload)
                    size_kb = len(payload) / 1024
                    if size_kb >= 1024:
                        size_str = f"{size_kb / 1024:.1f} MB"
                    else:
                        size_str = f"{size_kb:.1f} KB"
                    saved_files.append(f"- {filepath} ({size_str})")
                except Exception as e:
                    saved_files.append(f"- Error saving '{filename}': {str(e)}")

            if not saved_files:
                return ToolResult(
                    tool_name=self.name,
                    parameters=parameters,
                    result=f"No attachments found in email UID {message_uid}.",
                )

            result_text = (
                f"Downloaded {len(saved_files)} attachment(s) from email UID {message_uid}:\n"
                + "\n".join(saved_files)
            )

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
                result=f"Error: Failed to download attachments - {str(e)}",
            )

    def _decode_header_value(self, header_value: str) -> str:
        parts = decode_header(header_value)
        decoded_parts = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded_parts.append(part)
        return " ".join(decoded_parts)

    def _sanitize_filename(self, filename: str) -> str:
        filename = filename.replace("/", "_").replace("\\", "_")
        filename = re.sub(r'[<>:"|?*\x00-\x1f]', "_", filename)
        filename = filename.strip(". ")
        if len(filename) > 200:
            name, _, ext = filename.rpartition(".")
            if ext and len(ext) <= 10:
                filename = name[: 200 - len(ext) - 1] + "." + ext
            else:
                filename = filename[:200]
        return filename

    def _unique_filepath(self, directory: str, filename: str) -> str:
        filepath = os.path.join(directory, filename)
        if not os.path.exists(filepath):
            return filepath

        name, dot, ext = filename.rpartition(".")
        if not dot:
            name = filename
            ext = ""

        counter = 1
        while True:
            if ext:
                new_filename = f"{name}_{counter}.{ext}"
            else:
                new_filename = f"{name}_{counter}"
            filepath = os.path.join(directory, new_filename)
            if not os.path.exists(filepath):
                return filepath
            counter += 1
