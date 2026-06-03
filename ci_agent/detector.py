"""ProjectDetector: infer test runner, linter, build tool, and deployment target."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProjectInfo:
    """Summary of detected project characteristics."""

    language: str = "unknown"
    runtime_version: Optional[str] = None
    test_runner: str = "unknown"
    linter: str = "unknown"
    formatter: str = "unknown"
    build_tool: str = "unknown"
    package_manager: str = "unknown"
    deployment_target: str = "unknown"
    frameworks: list[str] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)


class ProjectDetector:
    """
    Heuristic detector that reads common config files to infer project tooling.

    Supports Python, Node/TypeScript, Go, Java/Kotlin, and Rust projects.
    """

    def __init__(self, directory: str) -> None:
        self.root = Path(directory)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def detect(self) -> ProjectInfo:
        """Run all detectors and return a combined ProjectInfo."""
        info = ProjectInfo()

        # Language detection is the foundation
        self._detect_language(info)

        # Dispatch to language-specific detectors
        if info.language == "python":
            self._detect_python(info)
        elif info.language in ("javascript", "typescript"):
            self._detect_node(info)
        elif info.language == "go":
            self._detect_go(info)
        elif info.language == "java":
            self._detect_java(info)
        elif info.language == "rust":
            self._detect_rust(info)

        # Deployment target (language-agnostic checks)
        self._detect_deployment(info)

        return info

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def _detect_language(self, info: ProjectInfo) -> None:
        root = self.root

        if (root / "pyproject.toml").exists() or (root / "setup.py").exists() or (root / "setup.cfg").exists() or (root / "requirements.txt").exists():
            info.language = "python"
            return

        if (root / "package.json").exists():
            # Distinguish TS vs JS
            if (root / "tsconfig.json").exists() or self._glob_exists("**/*.ts"):
                info.language = "typescript"
            else:
                info.language = "javascript"
            return

        if (root / "go.mod").exists():
            info.language = "go"
            return

        if (root / "pom.xml").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
            info.language = "java"
            return

        if (root / "Cargo.toml").exists():
            info.language = "rust"
            return

    # ------------------------------------------------------------------
    # Python
    # ------------------------------------------------------------------

    def _detect_python(self, info: ProjectInfo) -> None:
        info.package_manager = "pip"
        info.build_tool = "setuptools"
        info.test_runner = "pytest"  # reasonable default
        info.linter = "flake8"
        info.formatter = "black"

        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8", errors="replace")
            info.build_tool = self._first_match(
                text,
                [
                    (r'build-backend\s*=\s*"poetry', "poetry"),
                    (r'build-backend\s*=\s*"hatchling', "hatch"),
                    (r'build-backend\s*=\s*"flit', "flit"),
                    (r'build-backend\s*=\s*"setuptools', "setuptools"),
                ],
                info.build_tool,
            )
            if "[tool.poetry]" in text:
                info.package_manager = "poetry"
            elif "[tool.hatch]" in text:
                info.package_manager = "hatch"

            # Test runner
            info.test_runner = self._first_match(
                text,
                [
                    (r"\bpytest\b", "pytest"),
                    (r"\bunittest\b", "unittest"),
                    (r"\bhypothesis\b", "pytest"),
                ],
                info.test_runner,
            )

            # Linter / formatter
            if "[tool.ruff]" in text:
                info.linter = "ruff"
                info.formatter = "ruff"
            if "[tool.black]" in text:
                info.formatter = "black"
            if "[tool.mypy]" in text:
                info.extra["type_checker"] = "mypy"

        # Pipfile -> pipenv
        if (self.root / "Pipfile").exists():
            info.package_manager = "pipenv"

        # .python-version
        pv = self.root / ".python-version"
        if pv.exists():
            info.runtime_version = pv.read_text().strip()

        # Detect frameworks
        req_files = ["requirements.txt", "requirements-dev.txt", "Pipfile"]
        all_deps = self._read_files_concat(req_files)
        for pkg, framework in [
            ("django", "django"),
            ("flask", "flask"),
            ("fastapi", "fastapi"),
            ("starlette", "starlette"),
        ]:
            if re.search(pkg, all_deps, re.IGNORECASE):
                info.frameworks.append(framework)

    # ------------------------------------------------------------------
    # Node / TypeScript
    # ------------------------------------------------------------------

    def _detect_node(self, info: ProjectInfo) -> None:
        info.build_tool = "npm"
        info.package_manager = "npm"
        info.test_runner = "jest"
        info.linter = "eslint"
        info.formatter = "prettier"

        pkg_json = self.root / "package.json"
        if not pkg_json.exists():
            return

        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return

        # Package manager
        if (self.root / "yarn.lock").exists():
            info.package_manager = "yarn"
            info.build_tool = "yarn"
        elif (self.root / "pnpm-lock.yaml").exists():
            info.package_manager = "pnpm"
            info.build_tool = "pnpm"
        elif (self.root / "bun.lockb").exists():
            info.package_manager = "bun"
            info.build_tool = "bun"

        all_deps: dict[str, str] = {}
        all_deps.update(pkg.get("dependencies", {}))
        all_deps.update(pkg.get("devDependencies", {}))

        # Test runner
        if "vitest" in all_deps:
            info.test_runner = "vitest"
        elif "jest" in all_deps or "@jest/core" in all_deps:
            info.test_runner = "jest"
        elif "mocha" in all_deps:
            info.test_runner = "mocha"
        elif "tap" in all_deps:
            info.test_runner = "tap"

        # Linter
        if "eslint" in all_deps:
            info.linter = "eslint"
        elif "tslint" in all_deps:
            info.linter = "tslint"
        elif "biome" in all_deps or "@biomejs/biome" in all_deps:
            info.linter = "biome"
            info.formatter = "biome"

        # Formatter
        if "prettier" in all_deps:
            info.formatter = "prettier"

        # Build tool
        for tool in ("vite", "webpack", "rollup", "esbuild", "turbo", "nx"):
            if tool in all_deps:
                info.build_tool = tool
                break

        # Node version
        engines = pkg.get("engines", {})
        if "node" in engines:
            info.runtime_version = engines["node"]

        # Framework detection
        for pkg_name, framework in [
            ("react", "react"),
            ("vue", "vue"),
            ("@angular/core", "angular"),
            ("svelte", "svelte"),
            ("next", "next.js"),
            ("nuxt", "nuxt"),
            ("express", "express"),
            ("fastify", "fastify"),
        ]:
            if pkg_name in all_deps:
                info.frameworks.append(framework)

    # ------------------------------------------------------------------
    # Go
    # ------------------------------------------------------------------

    def _detect_go(self, info: ProjectInfo) -> None:
        info.package_manager = "go modules"
        info.build_tool = "go"
        info.test_runner = "go test"
        info.linter = "golangci-lint"
        info.formatter = "gofmt"

        go_mod = self.root / "go.mod"
        if go_mod.exists():
            text = go_mod.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^go\s+([\d.]+)", text, re.MULTILINE)
            if m:
                info.runtime_version = m.group(1)

        if (self.root / ".golangci.yml").exists() or (self.root / ".golangci.yaml").exists():
            info.linter = "golangci-lint"

    # ------------------------------------------------------------------
    # Java / Kotlin
    # ------------------------------------------------------------------

    def _detect_java(self, info: ProjectInfo) -> None:
        info.test_runner = "junit"
        info.linter = "checkstyle"
        info.formatter = "google-java-format"

        if (self.root / "pom.xml").exists():
            info.build_tool = "maven"
            info.package_manager = "maven"
        elif (self.root / "build.gradle.kts").exists():
            info.build_tool = "gradle"
            info.package_manager = "gradle"
            info.language = "kotlin"
        elif (self.root / "build.gradle").exists():
            info.build_tool = "gradle"
            info.package_manager = "gradle"

        # Check for Spring Boot
        for name in ("pom.xml", "build.gradle", "build.gradle.kts"):
            f = self.root / name
            if f.exists() and "spring-boot" in f.read_text(encoding="utf-8", errors="replace"):
                info.frameworks.append("spring-boot")
                break

    # ------------------------------------------------------------------
    # Rust
    # ------------------------------------------------------------------

    def _detect_rust(self, info: ProjectInfo) -> None:
        info.package_manager = "cargo"
        info.build_tool = "cargo"
        info.test_runner = "cargo test"
        info.linter = "clippy"
        info.formatter = "rustfmt"

        cargo_toml = self.root / "Cargo.toml"
        if cargo_toml.exists():
            text = cargo_toml.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'rust-version\s*=\s*"([^"]+)"', text)
            if m:
                info.runtime_version = m.group(1)

    # ------------------------------------------------------------------
    # Deployment target (language-agnostic)
    # ------------------------------------------------------------------

    def _detect_deployment(self, info: ProjectInfo) -> None:
        root = self.root
        checks = [
            ("Dockerfile", "docker"),
            ("docker-compose.yml", "docker-compose"),
            ("docker-compose.yaml", "docker-compose"),
            ("kubernetes", "kubernetes"),
            ("k8s", "kubernetes"),
            ("helm", "helm"),
            (".elasticbeanstalk", "aws-elastic-beanstalk"),
            ("app.yaml", "google-app-engine"),
            ("serverless.yml", "serverless-framework"),
            ("serverless.yaml", "serverless-framework"),
            ("netlify.toml", "netlify"),
            ("vercel.json", "vercel"),
            (".vercel", "vercel"),
            ("fly.toml", "fly.io"),
            ("render.yaml", "render"),
            ("railway.json", "railway"),
            ("Procfile", "heroku"),
        ]
        for name, target in checks:
            if (root / name).exists():
                info.deployment_target = target
                return
        # Check for Terraform
        if any(root.glob("*.tf")):
            info.deployment_target = "terraform"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _glob_exists(self, pattern: str) -> bool:
        return any(self.root.glob(pattern))

    def _first_match(
        self,
        text: str,
        patterns: list[tuple[str, str]],
        default: str,
    ) -> str:
        for pattern, value in patterns:
            if re.search(pattern, text):
                return value
        return default

    def _read_files_concat(self, filenames: list[str]) -> str:
        parts: list[str] = []
        for name in filenames:
            p = self.root / name
            if p.exists():
                parts.append(p.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(parts)
