"""Standard tool schemas in Anthropic tool-use format.

Each entry is a dict with ``name``, ``description``, and ``input_schema``
keys so it can be passed directly to :pymeth:`LLMProvider.call` or
:pymeth:`LLMProvider.call_multi_turn` via the ``tools`` parameter.

Usage::

    from crazypumpkin.llm.tools import STANDARD_TOOLS

    provider.call("Do something", tools=STANDARD_TOOLS)
"""

from __future__ import annotations

STANDARD_TOOLS: list[dict] = [
    {
        "name": "Read",
        "description": "Read the contents of a file at the given absolute path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (1-based).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read.",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "Edit",
        "description": "Replace an exact string in a file with a new string.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to modify.",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace.",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "If true, replace all occurrences instead of just the first.",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "Write",
        "description": "Write content to a file, creating or overwriting it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file.",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "Bash",
        "description": "Execute a shell command and return its output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds (default 120000).",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for the command.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "Grep",
        "description": "Search file contents using a regular expression pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in.",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.py').",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "Output mode: matching lines, file paths, or counts.",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "Glob",
        "description": "Find files matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files (e.g. '**/*.py').",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in.",
                },
            },
            "required": ["pattern"],
        },
    },
]
