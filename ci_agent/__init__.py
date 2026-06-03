"""ci-agent: AI-powered GitHub Actions CI/CD workflow generator."""

from ci_agent.agent import CiAgent
from ci_agent.detector import ProjectDetector

__all__ = ["CiAgent", "ProjectDetector"]
__version__ = "0.1.0"
