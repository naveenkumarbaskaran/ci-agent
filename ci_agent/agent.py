"""CiAgent: Uses Claude to read a project and generate GitHub Actions CI/CD workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

from ci_agent.detector import ProjectDetector, ProjectInfo

# ---------------------------------------------------------------------------
# Tool implementations (executed locally when Claude requests them)
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    """Read a file and return its content as a string."""
    p = Path(path)
    if not p.exists():
        return f"ERROR: File not found: {path}"
    if not p.is_file():
        return f"ERROR: Path is not a file: {path}"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"ERROR reading {path}: {exc}"


def _list_files(directory: str) -> str:
    """List files in a directory (non-recursive, relative paths)."""
    d = Path(directory)
    if not d.exists():
        return f"ERROR: Directory not found: {directory}"
    if not d.is_dir():
        return f"ERROR: Path is not a directory: {directory}"
    entries = sorted(d.iterdir())
    lines = []
    for entry in entries:
        kind = "dir" if entry.is_dir() else "file"
        lines.append(f"{kind}: {entry.name}")
    return "\n".join(lines) if lines else "(empty directory)"


def _write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} bytes to {path}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR writing {path}: {exc}"


def _detect_test_framework(directory: str) -> str:
    """Run ProjectDetector on a directory and return a JSON summary."""
    detector = ProjectDetector(directory)
    info: ProjectInfo = detector.detect()
    return json.dumps(info.__dict__, indent=2)


# Map tool names -> callables
_TOOL_HANDLERS: dict[str, Any] = {
    "read_file": lambda args: _read_file(args["path"]),
    "list_files": lambda args: _list_files(args["dir"]),
    "write_file": lambda args: _write_file(args["path"], args["content"]),
    "detect_test_framework": lambda args: _detect_test_framework(args["dir"]),
}

# ---------------------------------------------------------------------------
# Tool schema definitions (passed to Claude)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read the text content of a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and subdirectories in a directory (one level deep).",
        "input_schema": {
            "type": "object",
            "properties": {
                "dir": {
                    "type": "string",
                    "description": "Path to the directory to list.",
                }
            },
            "required": ["dir"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file, creating parent directories if necessary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Destination file path.",
                },
                "content": {
                    "type": "string",
                    "description": "The full text content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "detect_test_framework",
        "description": (
            "Detect the test runner, linter, build tool, and deployment target "
            "used in a project directory. Returns a JSON object with the findings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dir": {
                    "type": "string",
                    "description": "Root directory of the project to inspect.",
                }
            },
            "required": ["dir"],
        },
    },
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are ci-agent, an expert DevOps engineer specialising in GitHub Actions CI/CD.

Your job:
1. Explore the project at the provided source directory using the available tools.
2. Understand what language/runtime, test framework, linter, build tool, and
   deployment target the project uses.
3. Generate four GitHub Actions workflow YAML files and write them to the output
   directory:
   - test.yml      : run tests on every push / pull request
   - lint.yml      : run the linter / formatter on every push / pull request
   - deploy.yml    : build and deploy on push to main/master
   - pr_check.yml  : fast quality gate (tests + lint) triggered on pull requests

Guidelines for generated workflows:
- Always pin action versions (e.g. actions/checkout@v4).
- Use caching (actions/cache or built-in caches) where relevant.
- Include sensible defaults (timeout-minutes, continue-on-error where appropriate).
- If you cannot determine a specific tool, use a reasonable default for the
  detected language (e.g. pytest for Python, jest for Node.js).
- Write clean, well-commented YAML.
- After writing all files, provide a short summary of what you detected and what
  workflows you generated.
"""

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class CiAgent:
    """AI agent that inspects a project and writes GitHub Actions workflows."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8192,
        verbose: bool = False,
    ) -> None:
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.model = model
        self.max_tokens = max_tokens
        self.verbose = verbose

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(
        self,
        src_dir: str,
        output_dir: str,
        target: str = "github-actions",
    ) -> str:
        """
        Inspect *src_dir* and write CI/CD workflow files into *output_dir*.

        Returns the final text reply from the agent.
        """
        src_path = str(Path(src_dir).resolve())
        out_path = str(Path(output_dir).resolve())

        user_message = (
            f"Project source directory: {src_path}\n"
            f"Output directory for workflow files: {out_path}\n"
            f"CI/CD target platform: {target}\n\n"
            "Please explore the project, then generate and write the four workflow "
            "files (test.yml, lint.yml, deploy.yml, pr_check.yml) to the output directory."
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]

        # Agentic loop
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,  # type: ignore[arg-type]
                messages=messages,
            )

            if self.verbose:
                print(f"[agent] stop_reason={response.stop_reason}")

            # Append the assistant turn to history
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract the final text reply
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return ""

            if response.stop_reason == "tool_use":
                tool_results: list[dict[str, Any]] = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_name: str = block.name
                    tool_input: dict[str, Any] = block.input  # type: ignore[assignment]

                    if self.verbose:
                        print(f"[tool] {tool_name}({tool_input})")

                    handler = _TOOL_HANDLERS.get(tool_name)
                    if handler is None:
                        result_content = f"ERROR: Unknown tool '{tool_name}'"
                    else:
                        try:
                            result_content = handler(tool_input)
                        except Exception as exc:  # noqa: BLE001
                            result_content = f"ERROR executing {tool_name}: {exc}"

                    if self.verbose:
                        preview = str(result_content)[:200].replace("\n", " ")
                        print(f"[tool result] {preview}...")

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result_content),
                        }
                    )

                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason
            break

        return "Agent stopped unexpectedly."
