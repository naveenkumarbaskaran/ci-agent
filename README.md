# ci-agent-ai

An AI agent powered by [Anthropic Claude](https://www.anthropic.com/claude) that
inspects your project and automatically generates GitHub Actions CI/CD workflow
files tailored to your stack.

## Features

- Detects language, test runner, linter, build tool, and deployment target
- Generates four ready-to-use GitHub Actions workflows:
  - `test.yml` — run tests on every push / pull request
  - `lint.yml` — run the linter / formatter
  - `deploy.yml` — build and deploy on push to `main`
  - `pr_check.yml` — fast quality gate on pull requests
- Supports Python, Node.js/TypeScript, Go, Java/Kotlin, and Rust projects
- Uses Claude's agentic tool-use loop to explore the project before generating

## Installation

```bash
pip install ci-agent-ai
```

Or for development:

```bash
git clone https://github.com/example/ci-agent-ai
cd ci-agent-ai
pip install -e ".[dev]"
```

## Quick Start

```bash
export ANTHROPIC_API_KEY="sk-ant-..."

# Generate workflows for the current directory
ci-agent generate

# Specify a different source and output directory
ci-agent generate --src /path/to/myproject --output /path/to/myproject/.github/workflows

# See what the detector finds without generating anything
ci-agent detect /path/to/myproject

# Verbose output to see every tool call
ci-agent generate --verbose
```

## Command Reference

### `ci-agent generate`

```
Usage: ci-agent generate [OPTIONS]

  Inspect a project and generate GitHub Actions CI/CD workflows.

Options:
  --src PATH      Source directory to inspect.  [default: .]
  --output PATH   Output directory for generated workflow files.
                  [default: .github/workflows]
  --target TEXT   CI/CD platform target.  [default: github-actions]
  --model TEXT    Anthropic model to use.  [default: claude-sonnet-4-6]
  -v, --verbose   Print tool calls and intermediate results.
  --api-key TEXT  Anthropic API key (defaults to ANTHROPIC_API_KEY env var).
  --help          Show this message and exit.
```

### `ci-agent detect`

```
Usage: ci-agent detect [DIRECTORY]

  Detect project tooling without generating workflows.

Arguments:
  DIRECTORY  Project directory to inspect.  [default: .]
```

## Programmatic Usage

```python
from ci_agent import CiAgent, ProjectDetector

# Detect project info only
detector = ProjectDetector("/path/to/project")
info = detector.detect()
print(info.language, info.test_runner, info.linter)

# Generate workflows
agent = CiAgent(verbose=True)
summary = agent.generate(
    src_dir="/path/to/project",
    output_dir="/path/to/project/.github/workflows",
)
print(summary)
```

## Architecture

```
ci_agent/
  __init__.py      # Public API exports
  agent.py         # CiAgent: agentic loop using Anthropic SDK + tool use
  detector.py      # ProjectDetector: heuristic project analysis
  cli.py           # Click-based CLI with Rich output
```

### How It Works

1. **CLI** (`cli.py`) parses arguments and calls `CiAgent.generate()`.
2. **CiAgent** (`agent.py`) sends a prompt to Claude with four tools:
   - `read_file(path)` — read any file in the project
   - `list_files(dir)` — list directory contents
   - `write_file(path, content)` — write a workflow YAML file
   - `detect_test_framework(dir)` — run `ProjectDetector` and return JSON
3. Claude iteratively calls these tools to explore the project and then writes
   the four workflow files to the output directory.
4. **ProjectDetector** (`detector.py`) provides fast, heuristic-based detection
   by reading `pyproject.toml`, `package.json`, `go.mod`, `pom.xml`, etc.

## Environment Variables

| Variable           | Description                  |
|--------------------|------------------------------|
| `ANTHROPIC_API_KEY`| Your Anthropic API key       |

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)

## License

MIT
