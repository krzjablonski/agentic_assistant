import os

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from tools.fs_utils import resolve_safe_path
from config_service import config_service

DEFAULT_LIMIT = 2000
MAX_LINE_LENGTH = 2000


class ReadFileTool(ITool):
    def __init__(self):
        super().__init__(
            name="read_file",
            description=(
                "Read the text contents of a file within the configured base directory. "
                "The path must be relative to the base directory. "
                f"Returns content with line numbers. By default reads up to {DEFAULT_LIMIT} lines from the beginning."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    required=True,
                    default=None,
                    description="Relative path to the file, e.g. 'notes/summary.txt' or 'data.csv'.",
                ),
                ToolParameter(
                    name="offset",
                    type="integer",
                    required=False,
                    default=None,
                    description="Line number to start reading from (1-based). Only provide if the file is too large to read at once.",
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    required=False,
                    default=DEFAULT_LIMIT,
                    description=f"Number of lines to read. Defaults to {DEFAULT_LIMIT}.",
                ),
                ToolParameter(
                    name="encoding",
                    type="string",
                    required=False,
                    default="utf-8",
                    description="Text encoding to use when reading (default: utf-8).",
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)

        relative_path = args["path"]
        offset = args.get("offset")
        limit = args.get("limit", DEFAULT_LIMIT)
        encoding = args.get("encoding", "utf-8")

        if offset is not None and offset < 1:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: offset must be >= 1.",
                is_error=True,
            )
        if limit is not None and limit < 1:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="Error: limit must be >= 1.",
                is_error=True,
            )

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
                    result=f"Error: '{relative_path}' is not a file (it may be a directory).",
                    is_error=True,
                )

            with open(abs_path, "r", encoding=encoding, errors="replace") as f:
                all_lines = f.readlines()

            total_lines = len(all_lines)
            start_idx = (offset - 1) if offset is not None else 0
            end_idx = start_idx + (limit if limit is not None else DEFAULT_LIMIT)

            selected_lines = all_lines[start_idx:end_idx]
            actual_end = min(end_idx, total_lines)
            width = len(str(actual_end))

            formatted = []
            for i, line in enumerate(selected_lines):
                line_num = start_idx + i + 1
                content = line.rstrip("\n")
                if len(content) > MAX_LINE_LENGTH:
                    content = content[:MAX_LINE_LENGTH] + "... [truncated]"
                formatted.append(f"{str(line_num).rjust(width)}\t{content}")

            result = "\n".join(formatted)

            if start_idx > 0 or actual_end < total_lines:
                header = f"[File: {relative_path} (lines {start_idx + 1}-{actual_end} of {total_lines})]\n"
                result = header + result

            return ToolResult(tool_name=self.name, parameters=args, result=result)

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to read '{relative_path}' — {str(e)}",
                is_error=True,
            )
