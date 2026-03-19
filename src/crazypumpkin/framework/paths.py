import os
import re
from pathlib import Path


def get_project_root() -> Path:
    """Walk up from cwd and return the first directory containing config.yaml."""
    current = Path.cwd().resolve()
    for directory in [current, *current.parents]:
        if (directory / "config.yaml").is_file():
            return directory
    raise FileNotFoundError(
        "No config.yaml found in any ancestor directory of " + str(current)
    )


def resolve_path(path_str: str, project_root: Path) -> Path:
    """Resolve a path string to an absolute Path.

    Handles ~ home expansion, ${VAR_NAME} environment variable substitution,
    and resolves relative paths against project_root.
    """
    # Substitute ${VAR_NAME} patterns with environment variable values
    result = re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), m.group(0)),
        path_str,
    )

    # Expand ~ to user home directory
    path = Path(os.path.expanduser(result))

    # Resolve relative paths against project_root
    if not path.is_absolute():
        path = project_root / path

    return path.resolve()
