from __future__ import annotations

from dataclasses import dataclass
import re

from personal_ops.inbox_triage.schema import DraftReply, InboxTriageResponse, TriageItem


PRIORITY_CRITICAL = "Critical"
PRIORITY_QUICK_REPLY = "Quick Reply"
PRIORITY_DEFER = "Deferred"

ACTION_DRAFT_REPLY = "Draft reply"
ACTION_FOLLOW_UP = "Follow-up task"
ACTION_NO_REPLY = "No reply needed"

PRIORITY_TO_SCHEMA = {
    PRIORITY_CRITICAL: "critical",
    PRIORITY_QUICK_REPLY: "quick_reply",
    PRIORITY_DEFER: "deferred",
}

ACTION_TO_SCHEMA = {
    ACTION_DRAFT_REPLY: "draft_reply",
    ACTION_FOLLOW_UP: "follow_up_task",
    ACTION_NO_REPLY: "no_reply_needed",
}


@dataclass(frozen=True)
class InboxScenario:
    id: str
    title: str
    sender: str
    subject: str
    body: str
    expected_priority: str
    expected_action: str
    expected_reason: str
    expected_draft: str | None = None
    draft_must_include: tuple[str, ...] = ()
    draft_must_avoid: tuple[str, ...] = ()
    expected_follow_up: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def identifier(self) -> str:
        return f"From: {self.sender} | Subject: {self.subject}"


INBOX_TRIAGE_SCENARIOS: tuple[InboxScenario, ...] = (
    InboxScenario(
        id="client-deadline-decision",
        title="Client deadline with blocked decision",
        sender="Marta Zielinska <marta@client.example>",
        subject="Decyzja do 15:00: zakres wdrozenia",
        body=(
            "Czesc, potrzebujemy Twojej decyzji do 15:00, czy wchodzimy w zakres "
            "A czy B. Bez tego zespol nie moze zamknac planu na jutro."
        ),
        expected_priority=PRIORITY_CRITICAL,
        expected_action=ACTION_DRAFT_REPLY,
        expected_reason="blocks the client decision with a deadline today",
        expected_draft=(
            "Czesc Marta, wybieram zakres A. Prosze zamknijcie plan na tej podstawie; "
            "jesli widzicie ryzyko po stronie terminu, dajcie znac do 16:00."
        ),
        draft_must_include=("zakres A", "16:00"),
        draft_must_avoid=("zakres B",),
        tags=("urgent", "client", "decision", "draft"),
    ),
    InboxScenario(
        id="calendar-confirmation",
        title="Meeting time confirmation",
        sender="Piotr Nowak <piotr@partner.example>",
        subject="Potwierdzenie spotkania jutro 10:30",
        body=(
            "Hej, czy jutro 10:30 nadal Ci pasuje? Jesli tak, podesle finalna agende."
        ),
        expected_priority=PRIORITY_QUICK_REPLY,
        expected_action=ACTION_DRAFT_REPLY,
        expected_reason="direct question asking to confirm the meeting time",
        expected_draft=(
            "Czesc Piotr, potwierdzam jutro 10:30. Podeslij prosze finalna agende "
            "przed spotkaniem."
        ),
        draft_must_include=("10:30", "agende"),
        tags=("meeting", "confirmation", "draft"),
    ),
    InboxScenario(
        id="security-alert",
        title="Security alert with account review follow-up",
        sender="GitHub <noreply@github.com>",
        subject="Security alert: new SSH key added",
        body=(
            "A new SSH key was added to your account. If this was you, no action is "
            "required. If not, review your security settings."
        ),
        expected_priority=PRIORITY_DEFER,
        expected_action=ACTION_FOLLOW_UP,
        expected_reason="automated security alert with no reply to sender needed",
        expected_follow_up="review the GitHub account and confirm whether the SSH key was added intentionally",
        tags=("security", "automated", "follow-up", "no-reply"),
    ),
    InboxScenario(
        id="invoice-receipt",
        title="Invoice receipt to archive",
        sender="Fakturownia <no-reply@fakturownia.example>",
        subject="Faktura FV/04/2026",
        body=(
            "W zalaczeniu przesylamy fakture FV/04/2026. Termin platnosci: "
            "2026-05-10. Ta wiadomosc zostala wygenerowana automatycznie."
        ),
        expected_priority=PRIORITY_DEFER,
        expected_action=ACTION_FOLLOW_UP,
        expected_reason="automated invoice to handle operationally, no reply needed",
        expected_follow_up="save the invoice and add the payment to the finance checklist",
        tags=("invoice", "automated", "follow-up", "no-reply"),
    ),
    InboxScenario(
        id="newsletter",
        title="Informational newsletter",
        sender="10xDevs Newsletter <newsletter@10xdevs.example>",
        subject="Tygodniowe podsumowanie AI",
        body=(
            "W tym tygodniu zebralismy najciekawsze linki o AI, promptingu i "
            "automatyzacji. Milej lektury."
        ),
        expected_priority=PRIORITY_DEFER,
        expected_action=ACTION_NO_REPLY,
        expected_reason="informational newsletter, no response required",
        tags=("newsletter", "informational", "no-reply"),
    ),
    InboxScenario(
        id="system-status-update",
        title="Completed deployment status update",
        sender="Vercel <notifications@vercel.example>",
        subject="Deployment completed for personal-ops",
        body=(
            "The production deployment for personal-ops completed successfully at "
            "09:14 UTC. No errors were reported."
        ),
        expected_priority=PRIORITY_DEFER,
        expected_action=ACTION_NO_REPLY,
        expected_reason="status update about a completed event, no request for a reply",
        tags=("status", "automated", "no-reply"),
    ),
    InboxScenario(
        id="sales-spam",
        title="Cold outbound sales email",
        sender="Adam Sales <adam@sales-tool.example>",
        subject="Szybkie pytanie o automatyzacje leadow",
        body=(
            "Widze, ze rozwijasz produkt AI. Czy mozemy porozmawiac 15 minut o naszym "
            "narzedziu do automatyzacji leadow?"
        ),
        expected_priority=PRIORITY_DEFER,
        expected_action=ACTION_NO_REPLY,
        expected_reason="cold sales email with no operational value",
        tags=("spam", "sales", "no-reply"),
    ),
    InboxScenario(
        id="team-follow-up",
        title="Internal follow-up after meeting",
        sender="Anna Kowal <anna@company.example>",
        subject="Follow-up po dzisiejszym syncu",
        body=(
            "Po syncu zostaly dwie rzeczy: dopisac ownera do taska API i sprawdzic, "
            "czy demo na piatek wymaga dodatkowych danych. Nie musisz odpisywac, "
            "wystarczy ze to ogarniesz."
        ),
        expected_priority=PRIORITY_DEFER,
        expected_action=ACTION_FOLLOW_UP,
        expected_reason="specific post-meeting tasks, but no reply needed",
        expected_follow_up="add an owner to the API task and check the data needed for the demo",
        tags=("follow-up", "meeting", "no-reply"),
    ),
)


def get_inbox_triage_scenarios() -> tuple[InboxScenario, ...]:
    return INBOX_TRIAGE_SCENARIOS


def build_expected_triage_response(
    scenarios: tuple[InboxScenario, ...] = INBOX_TRIAGE_SCENARIOS,
) -> InboxTriageResponse:
    items: list[TriageItem] = []
    for scenario in scenarios:
        draft = None
        follow_up_task = None
        if scenario.expected_action == ACTION_DRAFT_REPLY:
            draft = DraftReply(
                to=_sender_email(scenario.sender),
                subject=f"Re: {scenario.subject}",
                body=scenario.expected_draft or "",
                status="created",
                reason=None,
            )
        elif scenario.expected_action == ACTION_FOLLOW_UP:
            follow_up_task = scenario.expected_follow_up
        items.append(
            TriageItem(
                sender=scenario.sender,
                subject=scenario.subject,
                priority=PRIORITY_TO_SCHEMA[scenario.expected_priority],
                action=ACTION_TO_SCHEMA[scenario.expected_action],
                rationale=scenario.expected_reason,
                draft=draft,
                follow_up_task=follow_up_task,
            )
        )

    return InboxTriageResponse(
        summary="Expected inbox triage scenario response.",
        items=items,
        warnings=[],
    )


def _sender_email(sender: str) -> str:
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1)
    return sender


def render_scenarios_markdown(
    scenarios: tuple[InboxScenario, ...] = INBOX_TRIAGE_SCENARIOS,
) -> str:
    lines = [
        "# Inbox Triage Test Scenarios",
        "",
        "Repeatable scenarios for manual and automated validation of the `Inbox triage` workflow.",
        "",
    ]
    for scenario in scenarios:
        lines.extend(
            [
                f"## {scenario.id}: {scenario.title}",
                "",
                f"- From: {scenario.sender}",
                f"- Subject: {scenario.subject}",
                f"- Tags: {', '.join(scenario.tags)}",
                f"- Expected priority: {scenario.expected_priority}",
                f"- Expected action: {scenario.expected_action}",
                f"- Expected reason: {scenario.expected_reason}",
            ]
        )
        if scenario.expected_draft:
            lines.append(f"- Expected draft: {scenario.expected_draft}")
        if scenario.draft_must_include:
            lines.append(
                f"- Draft must include: {', '.join(scenario.draft_must_include)}"
            )
        if scenario.draft_must_avoid:
            lines.append(f"- Draft must avoid: {', '.join(scenario.draft_must_avoid)}")
        if scenario.expected_follow_up:
            lines.append(f"- Expected follow-up: {scenario.expected_follow_up}")
        lines.extend(("", "Body:", "", f"> {scenario.body}", ""))
    return "\n".join(lines).rstrip() + "\n"
