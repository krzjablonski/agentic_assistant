import os

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from tools.fs_utils import resolve_safe_path
from config_service import config_service


class EditFileTool(ITool):
    def __init__(self):
        super().__init__(
            name="edit_file",
            description=(
                "Edit a file by replacing an exact string with new text. "
                "Use read_file first to see the exact content, then provide the fragment to replace. "
                "Fails if old_string is not found or appears multiple times (unless replace_all=true). "
                "Set new_string to an empty string to delete the fragment. "
                "The path must be relative to the configured base directory."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    required=True,
                    default=None,
                    description="Relative path to the file to edit, e.g. 'notes/draft.txt'.",
                ),
                ToolParameter(
                    name="old_string",
                    type="string",
                    required=True,
                    default=None,
                    description=(
                        "Exact text to find and replace. Must match the file content character-for-character, "
                        "including whitespace and newlines. Add surrounding context lines to make it unique."
                    ),
                ),
                ToolParameter(
                    name="new_string",
                    type="string",
                    required=True,
                    default=None,
                    description="Replacement text. Use an empty string to delete old_string.",
                ),
                ToolParameter(
                    name="replace_all",
                    type="boolean",
                    required=False,
                    default=False,
                    description=(
                        "If true, replace all occurrences of old_string. "
                        "If false (default), fail when old_string appears more than once."
                    ),
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)

        relative_path = args["path"]
        old_string = args["old_string"]
        new_string = args["new_string"]
        replace_all = args.get("replace_all", False)

        base_dir = config_service.get("filesystem.base_dir")
        abs_path, error = resolve_safe_path(base_dir, relative_path)
        if error:
            return ToolResult(tool_name=self.name, parameters=args, result=error, is_error=True)

        try:
            if not os.path.exists(abs_path):
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"Error: File not found: '{relative_path}'.",
                    is_error=True,
                )

            if not os.path.isfile(abs_path):
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"Error: '{relative_path}' is not a file.",
                    is_error=True,
                )

            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            count = content.count(old_string)

            if count == 0:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"Error: old_string not found in '{relative_path}'.",
                    is_error=True,
                )

            if count > 1 and not replace_all:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=(
                        f"Error: Found {count} occurrences of old_string in '{relative_path}'. "
                        f"Add more surrounding context to make it unique, or set replace_all=true."
                    ),
                    is_error=True,
                )

            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            replaced = count if replace_all else 1
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Successfully replaced {replaced} occurrence(s) in '{relative_path}'.",
            )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to edit '{relative_path}' — {str(e)}",
                is_error=True,
            )
