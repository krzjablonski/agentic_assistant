import os

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from tools.fs_utils import resolve_safe_path
from config_service import config_service


class ListDirectoryTool(ITool):
    def __init__(self):
        super().__init__(
            name="list_directory",
            description=(
                "List the contents of a directory within the configured base directory. "
                "Use '.' or omit the path to list the base directory itself. "
                "The path must be relative to the base directory."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    required=False,
                    default=".",
                    description=(
                        "Relative path to the directory to list. "
                        "Defaults to '.' (the base directory itself)."
                    ),
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)

        relative_path = args.get("path", ".") or "."

        base_dir = config_service.get("filesystem.base_dir")
        abs_path, error = resolve_safe_path(base_dir, relative_path)
        if error:
            return ToolResult(tool_name=self.name, parameters=args, result=error, is_error=True)

        try:
            if not os.path.exists(abs_path):
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"Error: Directory not found: '{relative_path}'.",
                    is_error=True,
                )

            if not os.path.isdir(abs_path):
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"Error: '{relative_path}' is not a directory.",
                    is_error=True,
                )

            entries = sorted(os.listdir(abs_path))
            lines = []
            for name in entries:
                full = os.path.join(abs_path, name)
                if os.path.isdir(full):
                    lines.append(f"[DIR]  {name}/")
                else:
                    size_bytes = os.path.getsize(full)
                    if size_bytes >= 1024 * 1024:
                        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                    elif size_bytes >= 1024:
                        size_str = f"{size_bytes / 1024:.1f} KB"
                    else:
                        size_str = f"{size_bytes} B"
                    lines.append(f"[FILE] {name}  ({size_str})")

            if not lines:
                result = f"Directory '{relative_path}' is empty."
            else:
                result = f"Contents of '{relative_path}' ({len(lines)} item(s)):\n" + "\n".join(lines)

            return ToolResult(tool_name=self.name, parameters=args, result=result)

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to list '{relative_path}' — {str(e)}",
                is_error=True,
            )
