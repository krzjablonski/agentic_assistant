from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from enum import Enum


class PlanStepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    step_number: int
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    notes: str = ""

    def to_text(self) -> str:
        status_icons = {
            "pending": "[ ]",
            "in_progress": "[→]",
            "completed": "[✓]",
            "skipped": "[–]",
        }
        icon = status_icons[self.status.value]
        text = f"{icon} Step {self.step_number}: {self.description}"
        if self.notes:
            text += f"\n   Note: {self.notes}"
        return text


@dataclass
class AgentPlan:
    goal: str
    steps: List[PlanStep]
    created_at: datetime = field(default_factory=datetime.now)
    last_updated_at: datetime = field(default_factory=datetime.now)

    def to_text(self) -> str:
        status_icons = {
            "pending": "[ ]",
            "in_progress": "[→]",
            "completed": "[✓]",
            "skipped": "[–]",
        }
        lines = [f"## Current Plan\nGoal: {self.goal}\n"]
        for step in self.steps:
            icon = status_icons[step.status.value]
            lines.append(f"{icon} Step {step.step_number}: {step.description}")
            if step.notes:
                lines.append(f"   Note: {step.notes}")
        return "\n".join(lines)
