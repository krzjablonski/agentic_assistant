import smtplib
from email.mime.text import MIMEText

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from config_service import config_service


class SendEmailTool(ITool):
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    def __init__(self):
        super().__init__(
            name="send_email",
            description="Send an email to the user",
            parameters=[
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
        """Send an email via Gmail SMTP with App Password."""
        self.validate_parameters(parameters)

        to = config_service.get("email.to")
        sender = config_service.get("email.from")
        app_password = config_service.get("email.app_password")
        subject = parameters["subject"]
        body = parameters["body"]

        if not to:
            return ToolResult(
                tool_name=self.name,
                parameters=parameters,
                result="Error: Default Recipient is not configured. Check Settings.",
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

            with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT) as server:
                server.starttls()
                server.login(sender, app_password)
                server.sendmail(sender, to, message.as_string())

            return ToolResult(
                tool_name=self.name,
                parameters={"to": to, "subject": subject, "body": body},
                result=f"Email sent successfully to {to}.",
            )

        except smtplib.SMTPAuthenticationError:
            return ToolResult(
                tool_name=self.name,
                parameters={"to": to, "subject": subject, "body": body},
                result="Error: SMTP authentication failed. Check EMAIL_FROM and EMAIL_APP_PASSWORD.",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters={"to": to, "subject": subject, "body": body},
                result=f"Error: Failed to send email - {str(e)}",
            )
