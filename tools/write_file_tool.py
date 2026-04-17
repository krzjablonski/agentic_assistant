import os

from tool_framework.i_tool import ITool, ToolResult, ToolParameter
from tools.fs_utils import resolve_safe_path
from config_service import config_service


class WriteFileTool(ITool):
    def __init__(self):
        super().__init__(
            name="write_file",
            description=(
                "Write text content to a file within the configured base directory. "
                "Creates the file if it does not exist, or overwrites it if it does. "
                "Missing parent directories are created automatically. "
                "The path must be relative to the base directory."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    required=True,
                    default=None,
                    description="Relative path to the file, e.g. 'notes/draft.txt' or 'output.json'.",
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    required=True,
                    default=None,
                    description="The text content to write to the file.",
                ),
                ToolParameter(
                    name="encoding",
                    type="string",
                    required=False,
                    default="utf-8",
                    description="Text encoding to use when writing (default: utf-8).",
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)

        relative_path = args["path"]
        content = args["content"]
        encoding = args.get("encoding", "utf-8")

        base_dir = config_service.get("filesystem.base_dir")
        abs_path, error = resolve_safe_path(base_dir, relative_path)
        if error:
            return ToolResult(tool_name=self.name, parameters=args, result=error, is_error=True)

        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            with open(abs_path, "w", encoding=encoding) as f:
                f.write(content)

            size_kb = len(content.encode(encoding)) / 1024
            log_params = {**args, "content": f"<{len(content)} chars>"}
            return ToolResult(
                tool_name=self.name,
                parameters=log_params,
                result=f"Successfully wrote {size_kb:.1f} KB to '{relative_path}'.",
            )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to write '{relative_path}' — {str(e)}",
                is_error=True,
            )
