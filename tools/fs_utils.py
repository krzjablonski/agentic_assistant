import os


def resolve_safe_path(base_dir: str, relative_path: str) -> tuple[str | None, str | None]:
    """
    Resolve `relative_path` within `base_dir` safely.

    Returns (absolute_path, None) on success.
    Returns (None, error_message) if base_dir is not configured or the resolved
    path escapes the sandbox.

    Uses os.path.realpath() to expand symlinks before the prefix check,
    preventing traversal via '..', URL encoding, or symlink-based escapes.
    """
    if not base_dir:
        return None, (
            "Filesystem base directory is not configured. "
            "Set FILESYSTEM_BASE_DIR or configure it in Settings."
        )

    abs_base = os.path.realpath(os.path.abspath(base_dir))
    abs_target = os.path.realpath(os.path.abspath(os.path.join(abs_base, relative_path)))

    if not (abs_target == abs_base or abs_target.startswith(abs_base + os.sep)):
        return None, (
            f"Access denied: path '{relative_path}' resolves outside the allowed base directory."
        )

    return abs_target, None
