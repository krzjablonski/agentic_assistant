from __future__ import annotations

import re
from dataclasses import dataclass

from personal_ops.inbox_triage.scenarios import (
    ACTION_DRAFT_REPLY,
    ACTION_TO_SCHEMA,
    INBOX_TRIAGE_SCENARIOS,
    PRIORITY_TO_SCHEMA,
    InboxScenario,
)
from personal_ops.inbox_triage.schema import (
    TriageItem,
    coerce_inbox_triage_response,
)

DRAFT_PLACEHOLDER_RE = re.compile(
    r"(?i)(\[[^\]]+\]|<[^@\s>]+>|\.{3,}|\bTODO\b|\bTBD\b|uzupelnij|wstaw|do edycji)"
)
DRAFT_EXECUTION_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"wyslalem|wys\u0142a\u0142em|wyslalam|wys\u0142a\u0142am|"
    r"wyslane|wys\u0142ane|sent|dodalem|doda\u0142am|"
    r"zapisalem|zapisa\u0142am"
    r")\b"
)
MIN_DRAFT_WORDS = 8


@dataclass(frozen=True)
class DraftQualityIssue:
    code: str
    scenario_id: str
    identifier: str
    message: str


@dataclass(frozen=True)
class DraftQualityReport:
    issues: tuple[DraftQualityIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def evaluate_draft_quality(
    response: object,
    scenarios: tuple[InboxScenario, ...] = INBOX_TRIAGE_SCENARIOS,
) -> DraftQualityReport:
    issues: list[DraftQualityIssue] = []
    try:
        structured = coerce_inbox_triage_response(response)
    except Exception as exc:
        return DraftQualityReport(
            issues=(
                DraftQualityIssue(
                    code="structured_invalid",
                    scenario_id="__response__",
                    identifier="",
                    message=f"Triage response must satisfy InboxTriageResponse: {exc}",
                ),
            )
        )

    items_by_key = {
        _canonical_key(item.sender, item.subject): item for item in structured.items
    }

    for scenario in scenarios:
        item = items_by_key.get(_scenario_key(scenario))
        if item is None:
            issues.append(
                DraftQualityIssue(
                    code="missing_item",
                    scenario_id=scenario.id,
                    identifier=scenario.identifier,
                    message="Expected one structured item for this scenario.",
                )
            )
            continue

        _evaluate_priority_and_action(item, scenario, issues)
        _evaluate_draft_payload(item, scenario, issues)

    return DraftQualityReport(issues=tuple(issues))


def _evaluate_priority_and_action(
    item: TriageItem,
    scenario: InboxScenario,
    issues: list[DraftQualityIssue],
) -> None:
    expected_priority = PRIORITY_TO_SCHEMA[scenario.expected_priority]
    if item.priority != expected_priority:
        issues.append(
            DraftQualityIssue(
                code="wrong_priority",
                scenario_id=scenario.id,
                identifier=scenario.identifier,
                message=f"Expected priority `{expected_priority}`, got `{item.priority}`.",
            )
        )

    expected_action = ACTION_TO_SCHEMA[scenario.expected_action]
    if item.action != expected_action:
        code = (
            "missing_draft_action"
            if scenario.expected_action == ACTION_DRAFT_REPLY
            else "wrong_action"
        )
        issues.append(
            DraftQualityIssue(
                code=code,
                scenario_id=scenario.id,
                identifier=scenario.identifier,
                message=f"Expected action `{expected_action}`, got `{item.action}`.",
            )
        )


def _evaluate_draft_payload(
    item: TriageItem,
    scenario: InboxScenario,
    issues: list[DraftQualityIssue],
) -> None:
    if scenario.expected_action != ACTION_DRAFT_REPLY:
        if item.action == "draft_reply" or item.draft is not None:
            issues.append(
                DraftQualityIssue(
                    code="unexpected_draft",
                    scenario_id=scenario.id,
                    identifier=scenario.identifier,
                    message="Scenario should not get a reply draft.",
                )
            )
        return

    if item.action != "draft_reply":
        return

    if item.draft is None:
        issues.append(
            DraftQualityIssue(
                code="missing_draft_body",
                scenario_id=scenario.id,
                identifier=scenario.identifier,
                message="Expected a full editable draft.",
            )
        )
        return

    draft_text = item.draft.body
    words = re.findall(r"\b[\w:.-]+\b", draft_text)
    if len(words) < MIN_DRAFT_WORDS:
        issues.append(
            DraftQualityIssue(
                code="draft_too_short",
                scenario_id=scenario.id,
                identifier=scenario.identifier,
                message="Draft is too short to be work-ready.",
            )
        )
    if DRAFT_PLACEHOLDER_RE.search(draft_text):
        issues.append(
            DraftQualityIssue(
                code="draft_has_placeholder",
                scenario_id=scenario.id,
                identifier=scenario.identifier,
                message="Draft contains a placeholder instead of editable final text.",
            )
        )
    if DRAFT_EXECUTION_CLAIM_RE.search(draft_text):
        issues.append(
            DraftQualityIssue(
                code="draft_claims_execution",
                scenario_id=scenario.id,
                identifier=scenario.identifier,
                message="Draft implies an action was already executed.",
            )
        )
    for term in scenario.draft_must_include:
        if not _contains_term(draft_text, term):
            issues.append(
                DraftQualityIssue(
                    code="draft_missing_required_term",
                    scenario_id=scenario.id,
                    identifier=scenario.identifier,
                    message=f"Draft should include `{term}`.",
                )
            )
    for term in scenario.draft_must_avoid:
        if _contains_term(draft_text, term):
            issues.append(
                DraftQualityIssue(
                    code="draft_contains_forbidden_term",
                    scenario_id=scenario.id,
                    identifier=scenario.identifier,
                    message=f"Draft should avoid `{term}`.",
                )
            )


def _contains_term(text: str, term: str) -> bool:
    return term.casefold() in text.casefold()


def _scenario_key(scenario: InboxScenario) -> str:
    return _canonical_key(scenario.sender, scenario.subject)


def _canonical_key(sender: str, subject: str) -> str:
    return re.sub(r"\s+", " ", f"{sender} {subject}").strip().lower()
