import base64
import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(override=True)

try:
    from e2b import Sandbox
except ImportError:
    Sandbox = None


mcp = FastMCP("e2b")


@dataclass
class ManagedCommand:
    sandbox_id: str
    pid: int
    command: str
    cwd: str | None
    handle: Any


_SANDBOXES: dict[str, Any] = {}
_COMMANDS: dict[tuple[str, int], ManagedCommand] = {}


def _require_e2b() -> None:
    if Sandbox is None:
        raise RuntimeError(
            "Python package `e2b` is not installed. Install dependencies from "
            "`requirements.txt` and set `E2B_API_KEY` before using this server."
        )


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _get_sandbox_id(sandbox: Any) -> str:
    sandbox_id = getattr(sandbox, "sandbox_id", None)
    if sandbox_id:
        return str(sandbox_id)

    info = sandbox.get_info()
    resolved = getattr(info, "sandbox_id", None) or getattr(info, "id", None)
    if not resolved:
        raise RuntimeError("Unable to determine sandbox ID.")
    return str(resolved)


def _remember_sandbox(sandbox: Any) -> Any:
    sandbox_id = _get_sandbox_id(sandbox)
    _SANDBOXES[sandbox_id] = sandbox
    return sandbox


def _get_or_connect_sandbox(sandbox_id: str) -> Any:
    _require_e2b()
    sandbox = _SANDBOXES.get(sandbox_id)
    if sandbox is not None:
        return sandbox

    sandbox = Sandbox.connect(sandbox_id)
    _SANDBOXES[sandbox_id] = sandbox
    return sandbox


def _to_string_dict(raw_json: str | None, field_name: str) -> dict[str, str]:
    if not raw_json:
        return {}

    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"`{field_name}` must be valid JSON: {exc}") from exc

    if not isinstance(value, dict):
        raise ValueError(f"`{field_name}` must decode to a JSON object.")

    return {str(key): str(item) for key, item in value.items()}


def _decode_content(content: str, encoding: str) -> str | bytes:
    if encoding == "text":
        return content
    if encoding == "base64":
        try:
            return base64.b64decode(content.encode("utf-8"), validate=True)
        except Exception as exc:
            raise ValueError("Invalid base64 payload supplied in `content`.") from exc
    raise ValueError("`encoding` must be either `text` or `base64`.")


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (bytes, bytearray)):
        return {
            "type": "bytes",
            "base64": base64.b64encode(bytes(value)).decode("ascii"),
            "size": len(value),
        }

    if is_dataclass(value):
        return _serialize(asdict(value))

    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_serialize(item) for item in value]

    for method_name in ("model_dump", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _serialize(method())
            except TypeError:
                pass

    if hasattr(value, "__dict__"):
        public = {
            key: val
            for key, val in vars(value).items()
            if not key.startswith("_") and not callable(val)
        }
        if public:
            return _serialize(public)

    data: dict[str, Any] = {}
    for key in dir(value):
        if key.startswith("_"):
            continue
        try:
            attr = getattr(value, key)
        except Exception:
            continue
        if callable(attr):
            continue
        if isinstance(attr, (bool, int, float, str, bytes, bytearray, list, tuple, dict)):
            data[key] = _serialize(attr)
    return data or str(value)


def _command_snapshot(managed: ManagedCommand) -> dict[str, Any]:
    handle = managed.handle
    return {
        "sandbox_id": managed.sandbox_id,
        "pid": managed.pid,
        "command": managed.command,
        "cwd": managed.cwd,
        "running": getattr(handle, "exit_code", None) is None,
        "exit_code": getattr(handle, "exit_code", None),
        "stdout": _clean_text(getattr(handle, "stdout", "")),
        "stderr": _clean_text(getattr(handle, "stderr", "")),
        "error": _clean_text(getattr(handle, "error", "")),
    }


def _command_result_payload(
    sandbox_id: str,
    command: str,
    result: Any,
    *,
    background: bool = False,
) -> dict[str, Any]:
    payload = {
        "sandbox_id": sandbox_id,
        "command": command,
        "background": background,
        "exit_code": getattr(result, "exit_code", None),
        "stdout": _clean_text(getattr(result, "stdout", "")),
        "stderr": _clean_text(getattr(result, "stderr", "")),
        "error": _clean_text(getattr(result, "error", "")),
    }
    pid = getattr(result, "pid", None)
    if pid is not None:
        payload["pid"] = pid
    return payload


def _exception_payload(sandbox_id: str, command: str, exc: Exception) -> dict[str, Any]:
    return {
        "sandbox_id": sandbox_id,
        "command": command,
        "exit_code": getattr(exc, "exit_code", None),
        "stdout": _clean_text(getattr(exc, "stdout", "")),
        "stderr": _clean_text(getattr(exc, "stderr", "")),
        "error": _clean_text(getattr(exc, "error", "")) or str(exc),
    }


@mcp.tool()
def create_sandbox(
    timeout_seconds: int = 1800,
    template: str | None = None,
    metadata_json: str | None = None,
    env_json: str | None = None,
    secure: bool = True,
    allow_internet_access: bool = True,
) -> str:
    """Create a new E2B sandbox and return its ID plus metadata.

    Args:
        timeout_seconds: Sandbox timeout in seconds.
        template: Optional E2B template name or ID.
        metadata_json: Optional JSON object with sandbox metadata.
        env_json: Optional JSON object with global environment variables.
        secure: Whether to keep the sandbox access-token protected.
        allow_internet_access: Whether the sandbox can access the internet.
    """
    _require_e2b()
    sandbox = Sandbox.create(
        template=template,
        timeout=timeout_seconds,
        metadata=_to_string_dict(metadata_json, "metadata_json"),
        envs=_to_string_dict(env_json, "env_json"),
        secure=secure,
        allow_internet_access=allow_internet_access,
    )
    sandbox = _remember_sandbox(sandbox)
    info = sandbox.get_info()
    return _json_response(
        {
            "sandbox_id": _get_sandbox_id(sandbox),
            "timeout_seconds": timeout_seconds,
            "template": template or "base",
            "secure": secure,
            "allow_internet_access": allow_internet_access,
            "info": _serialize(info),
        }
    )


@mcp.tool()
def connect_sandbox(sandbox_id: str, timeout_seconds: int | None = None) -> str:
    """Connect to an existing sandbox by ID.

    Args:
        sandbox_id: Existing E2B sandbox ID.
        timeout_seconds: Optional timeout extension in seconds while connecting.
    """
    _require_e2b()
    sandbox = Sandbox.connect(sandbox_id, timeout=timeout_seconds)
    sandbox = _remember_sandbox(sandbox)
    return _json_response(
        {
            "sandbox_id": _get_sandbox_id(sandbox),
            "connected": True,
            "info": _serialize(sandbox.get_info()),
        }
    )


@mcp.tool()
def list_known_sandboxes() -> str:
    """List sandboxes currently known to this MCP server process."""
    sandboxes = []
    for sandbox_id, sandbox in _SANDBOXES.items():
        is_running = None
        try:
            is_running = sandbox.is_running()
        except Exception:
            is_running = None
        sandboxes.append(
            {
                "sandbox_id": sandbox_id,
                "running": is_running,
            }
        )
    return _json_response({"sandboxes": sandboxes, "count": len(sandboxes)})


@mcp.tool()
def get_sandbox_info(sandbox_id: str) -> str:
    """Return metadata about a sandbox.

    Args:
        sandbox_id: Sandbox ID to inspect.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    try:
        is_running = sandbox.is_running()
    except Exception:
        is_running = None
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "is_running": is_running,
            "info": _serialize(sandbox.get_info()),
        }
    )


@mcp.tool()
def set_sandbox_timeout(sandbox_id: str, timeout_seconds: int) -> str:
    """Update sandbox timeout.

    Args:
        sandbox_id: Sandbox ID to update.
        timeout_seconds: New timeout in seconds.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    sandbox.set_timeout(timeout_seconds)
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "timeout_seconds": timeout_seconds,
            "updated": True,
        }
    )


@mcp.tool()
def kill_sandbox(sandbox_id: str) -> str:
    """Kill a sandbox and forget cached handles for it.

    Args:
        sandbox_id: Sandbox ID to kill.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    killed = sandbox.kill()
    _SANDBOXES.pop(sandbox_id, None)

    to_remove = [key for key in _COMMANDS if key[0] == sandbox_id]
    for key in to_remove:
        _COMMANDS.pop(key, None)

    return _json_response({"sandbox_id": sandbox_id, "killed": bool(killed)})


@mcp.tool()
def run_command(
    sandbox_id: str,
    command: str,
    cwd: str | None = None,
    env_json: str | None = None,
    timeout_seconds: int = 120,
) -> str:
    """Run a shell command and wait for completion.

    Args:
        sandbox_id: Sandbox where the command should run.
        command: Shell command to execute.
        cwd: Optional working directory.
        env_json: Optional JSON object with environment variables.
        timeout_seconds: Command timeout in seconds.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    envs = _to_string_dict(env_json, "env_json")

    try:
        result = sandbox.commands.run(
            command,
            cwd=cwd,
            envs=envs or None,
            timeout=timeout_seconds,
        )
        return _json_response(_command_result_payload(sandbox_id, command, result))
    except Exception as exc:
        return _json_response(_exception_payload(sandbox_id, command, exc))


@mcp.tool()
def start_command(
    sandbox_id: str,
    command: str,
    cwd: str | None = None,
    env_json: str | None = None,
    timeout_seconds: int = 1800,
    open_stdin: bool = False,
) -> str:
    """Start a background command and keep a handle in this MCP process.

    Args:
        sandbox_id: Sandbox where the command should run.
        command: Shell command to execute.
        cwd: Optional working directory.
        env_json: Optional JSON object with environment variables.
        timeout_seconds: Background command timeout in seconds.
        open_stdin: Whether stdin should remain open for later writes.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    envs = _to_string_dict(env_json, "env_json")
    handle = sandbox.commands.run(
        command,
        background=True,
        cwd=cwd,
        envs=envs or None,
        stdin=open_stdin,
        timeout=timeout_seconds,
    )
    managed = ManagedCommand(
        sandbox_id=sandbox_id,
        pid=handle.pid,
        command=command,
        cwd=cwd,
        handle=handle,
    )
    _COMMANDS[(sandbox_id, handle.pid)] = managed
    return _json_response(_command_snapshot(managed))


@mcp.tool()
def get_command_status(sandbox_id: str, pid: int) -> str:
    """Read the latest known status and output of a background command.

    Args:
        sandbox_id: Sandbox ID that owns the command.
        pid: Process ID returned by `start_command`.
    """
    managed = _COMMANDS.get((sandbox_id, pid))
    if managed is None:
        raise ValueError(f"No tracked command for sandbox_id={sandbox_id!r}, pid={pid}.")
    return _json_response(_command_snapshot(managed))


@mcp.tool()
def wait_for_command(sandbox_id: str, pid: int) -> str:
    """Block until a tracked background command finishes.

    Args:
        sandbox_id: Sandbox ID that owns the command.
        pid: Process ID returned by `start_command`.
    """
    managed = _COMMANDS.get((sandbox_id, pid))
    if managed is None:
        raise ValueError(f"No tracked command for sandbox_id={sandbox_id!r}, pid={pid}.")

    try:
        result = managed.handle.wait()
        payload = _command_result_payload(
            sandbox_id,
            managed.command,
            result,
            background=True,
        )
    except Exception as exc:
        payload = _exception_payload(sandbox_id, managed.command, exc)
        payload["pid"] = pid
    return _json_response(payload)


@mcp.tool()
def send_command_stdin(sandbox_id: str, pid: int, data: str) -> str:
    """Send data to stdin of a background command.

    Args:
        sandbox_id: Sandbox ID that owns the command.
        pid: Process ID returned by `start_command`.
        data: Text to write to stdin.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    sandbox.commands.send_stdin(pid, data)
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "pid": pid,
            "stdin_bytes": len(data.encode("utf-8")),
            "sent": True,
        }
    )


@mcp.tool()
def kill_command(sandbox_id: str, pid: int) -> str:
    """Kill a running background command.

    Args:
        sandbox_id: Sandbox ID that owns the command.
        pid: Process ID returned by `start_command`.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    killed = sandbox.commands.kill(pid)
    _COMMANDS.pop((sandbox_id, pid), None)
    return _json_response({"sandbox_id": sandbox_id, "pid": pid, "killed": bool(killed)})


@mcp.tool()
def write_file(
    sandbox_id: str,
    path: str,
    content: str,
    encoding: Literal["text", "base64"] = "text",
) -> str:
    """Write a file into the sandbox.

    Args:
        sandbox_id: Target sandbox ID.
        path: Destination path inside the sandbox.
        content: File content as text or base64.
        encoding: `text` for UTF-8 text, `base64` for binary payloads.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    data = _decode_content(content, encoding)
    info = sandbox.files.write(path, data)
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "path": path,
            "encoding": encoding,
            "info": _serialize(info),
        }
    )


@mcp.tool()
def read_file(
    sandbox_id: str,
    path: str,
    encoding: Literal["text", "base64"] = "text",
) -> str:
    """Read a file from the sandbox.

    Args:
        sandbox_id: Target sandbox ID.
        path: File path inside the sandbox.
        encoding: `text` to return plaintext, `base64` to return raw bytes encoded as base64.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    if encoding == "text":
        content = sandbox.files.read(path, format="text")
        return _json_response(
            {
                "sandbox_id": sandbox_id,
                "path": path,
                "encoding": encoding,
                "content": content,
            }
        )

    content = sandbox.files.read(path, format="bytes")
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "path": path,
            "encoding": encoding,
            "content": base64.b64encode(bytes(content)).decode("ascii"),
        }
    )


@mcp.tool()
def list_files(sandbox_id: str, path: str = "/home/user", depth: int = 1) -> str:
    """List files and directories in the sandbox.

    Args:
        sandbox_id: Target sandbox ID.
        path: Directory path to inspect.
        depth: Recursive depth for listing.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    entries = sandbox.files.list(path, depth=depth)
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "path": path,
            "depth": depth,
            "entries": _serialize(entries),
        }
    )


@mcp.tool()
def get_path_info(sandbox_id: str, path: str) -> str:
    """Get metadata for a file or directory.

    Args:
        sandbox_id: Target sandbox ID.
        path: Path to inspect.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    info = sandbox.files.get_info(path)
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "path": path,
            "exists": sandbox.files.exists(path),
            "info": _serialize(info),
        }
    )


@mcp.tool()
def make_directory(sandbox_id: str, path: str) -> str:
    """Create a directory in the sandbox.

    Args:
        sandbox_id: Target sandbox ID.
        path: Directory path to create.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    created = sandbox.files.make_dir(path)
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "path": path,
            "created": bool(created),
        }
    )


@mcp.tool()
def rename_path(sandbox_id: str, old_path: str, new_path: str) -> str:
    """Rename or move a file/directory inside the sandbox.

    Args:
        sandbox_id: Target sandbox ID.
        old_path: Existing sandbox path.
        new_path: New sandbox path.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    info = sandbox.files.rename(old_path, new_path)
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "old_path": old_path,
            "new_path": new_path,
            "info": _serialize(info),
        }
    )


@mcp.tool()
def delete_path(sandbox_id: str, path: str) -> str:
    """Delete a file or directory from the sandbox.

    Args:
        sandbox_id: Target sandbox ID.
        path: Sandbox path to delete.
    """
    sandbox = _get_or_connect_sandbox(sandbox_id)
    sandbox.files.remove(path)
    return _json_response(
        {
            "sandbox_id": sandbox_id,
            "path": path,
            "deleted": True,
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
