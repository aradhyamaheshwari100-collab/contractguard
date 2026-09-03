"""
agents/base.py — Base class for all ContractGuard reasoning agents.
Wraps the Gemini API call with:
  - JSON-only output enforcement
  - Regex extraction of JSON from prose-contaminated output
  - Retry loop on malformed JSON (up to 3 attempts with stricter prompt)
  - Structured error handling → AgentFindings.insufficient()
"""
from __future__ import annotations
import json
import re
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any
import google.generativeai as genai
from models import AgentFindings
from config import settings

logger = logging.getLogger(__name__)

# Configure Gemini once at module load
genai.configure(api_key=settings.gemini_api_key)

MAX_LLM_RETRIES = 3
# Regex to extract the first {...} or [...] block from LLM output
JSON_EXTRACT_RE = re.compile(r'(\{[\s\S]*\}|\[[\s\S]*\])', re.MULTILINE)


class BaseAgent(ABC):
    """Abstract base for all ContractGuard reasoning agents."""

    agent_name: str = "base"
    model_name: str = settings.gemini_model

    def _get_model(self) -> genai.GenerativeModel:
        return genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=genai.GenerationConfig(
                temperature=0.1,   # Low temp for deterministic structured output
                top_p=0.95,
                max_output_tokens=2048,
            ),
        )

    async def _call_llm(self, prompt: str, extra_strict: bool = False) -> dict[str, Any]:
        """
        Call Gemini and return the parsed JSON dict.
        Retries up to MAX_LLM_RETRIES times if output is not valid JSON.
        """
        model = self._get_model()
        suffix = (
            "\n\n⚠ CRITICAL: Your previous response was not valid JSON. "
            "Return ONLY the raw JSON object. No markdown, no code fences, no explanation."
            if extra_strict else ""
        )
        full_prompt = prompt + suffix

        last_error: Exception | None = None
        for attempt in range(MAX_LLM_RETRIES):
            try:
                # Run in thread pool to avoid blocking the event loop
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: model.generate_content(full_prompt)
                )
                raw = response.text.strip()

                # Strip markdown code fences if present
                raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
                raw = re.sub(r'\s*```\s*$', '', raw, flags=re.MULTILINE)
                raw = raw.strip()

                # Try direct parse
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    # Try regex extraction of first JSON block
                    match = JSON_EXTRACT_RE.search(raw)
                    if match:
                        return json.loads(match.group(1))
                    raise

            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(
                    f"[{self.agent_name}] Attempt {attempt + 1}: JSON parse failed: {e}. Retrying."
                )
                extra_strict = True  # Stricter suffix on next attempt
                await asyncio.sleep(0.3)

            except Exception as e:
                last_error = e
                logger.error(f"[{self.agent_name}] LLM call failed: {e}")
                await asyncio.sleep(1.0)

        raise RuntimeError(
            f"[{self.agent_name}] Failed to get valid JSON from LLM after "
            f"{MAX_LLM_RETRIES} attempts. Last error: {last_error}"
        )

    def _parse_findings(self, raw: dict) -> AgentFindings:
        """
        Parse raw LLM dict into AgentFindings, handling missing/malformed fields.
        This is the safety net — never crash the orchestrator on bad agent output.
        """
        from models import Finding, FindingSeverity

        findings_raw = raw.get("findings", [])
        findings = []
        for item in findings_raw:
            try:
                severity_str = item.get("severity", "medium").lower()
                # Normalise unusual severity values
                severity_map = {
                    "critical": "critical", "high": "high",
                    "medium": "medium", "low": "low",
                    "info": "info", "informational": "info",
                    "warning": "medium", "warn": "medium",
                }
                severity = FindingSeverity(severity_map.get(severity_str, "medium"))
                findings.append(Finding(
                    severity=severity,
                    category=item.get("category", "unknown"),
                    title=item.get("title", "Unnamed finding"),
                    description=item.get("description", ""),
                    evidence=item.get("evidence"),
                    raw_snippet=item.get("raw_snippet"),
                    agent=self.agent_name,
                ))
            except Exception as e:
                logger.warning(f"[{self.agent_name}] Skipped malformed finding: {e}")

        score = int(raw.get("suspicion_score", 50))
        score = max(0, min(100, score))  # Clamp to [0, 100]

        return AgentFindings(
            agent=self.agent_name,
            suspicion_score=score,
            confidence=raw.get("confidence", "medium"),
            findings=findings,
            summary=raw.get("summary", ""),
            insufficient_data=raw.get("insufficient_data", False),
        )

    @abstractmethod
    async def run(self, **kwargs) -> AgentFindings:
        """Each agent implements its own run() method."""
        ...
