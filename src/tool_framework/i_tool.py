from typing import Any
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class ToolResult:
    tool_name: str
    parameters: dict
    result: str
    is_error: bool = False


@dataclass
class ToolParameter:
    name: str
    type: str
    required: bool
    default: any
    description: str


class ITool(ABC):
    def __init__(self, name: str, description: str, parameters: list[ToolParameter]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.input_schema: dict | None = None

    def __str__(self) -> str:
        return f"`{self.name}`: {self.description}"

    @abstractmethod
    async def run(self, args: dict[str, any]) -> ToolResult:
        pass

    def validate_parameters(self, args: dict[str, any]) -> None:
        """Validate args against declared parameters.

        Raises:
            ValueError: If validation fails, with a descriptive message for AI agent.
        """
        errors: list[str] = []
        declared_names = {param.name for param in self.parameters}
        provided_names = set(args.keys())

        unknown = provided_names - declared_names
        for name in sorted(unknown):
            errors.append(f"Unknown parameter '{name}'")

        type_map = {
            "str": str,
            "string": str,
            "int": int,
            "integer": int,
            "float": float,
            "bool": bool,
            "boolean": bool,
            "list": list,
            "dict": dict,
            "any": Any,
        }

        for param in self.parameters:
            if param.type.lower() == "any":
                continue
            if param.name not in args:
                if param.required:
                    errors.append(f"Missing required parameter '{param.name}'")
                continue

            value = args[param.name]
            if value is None:
                continue

            expected_type = type_map.get(param.type.lower())
            if expected_type and not isinstance(value, expected_type):
                errors.append(
                    f"Parameter '{param.name}' has wrong type: "
                    f"expected {param.type}, got {type(value).__name__}"
                )

        if errors:
            error_list = "; ".join(errors)
            raise ValueError(
                f"Tool '{self.name}' was called with invalid parameters. "
                f"Errors: {error_list}"
            )
