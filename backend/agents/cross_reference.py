"""
agents/cross_reference.py — Cross-Reference Agent.
Checks addresses against known scam databases.
Only invoked when suspicion score ≥ THRESHOLD_ESCALATE_CROSSREF.
"""
from __future__ import annotations
import json
from models import AgentFindings, ToolResult
from agents.base import BaseAgent

CROSSREF_PROMPT = """You are a threat intelligence analyst at ContractGuard.

Your task: Evaluate the results of cross-referencing addresses against known scam/fraud databases and determine the implications.

ADDRESSES CHECKED: {addresses}

CROSS-REFERENCE RESULTS:
{xref_data}

DATABASE SOURCES CHECKED:
- CryptoScamDB static list (community-reported scam addresses)
- GoPlus Security API (if available)

SCORING GUIDANCE:
- 0:     No matches found in any database
- 40-60: Match in lower-confidence source
- 70-85: Match in high-confidence source (CryptoScamDB)
- 86-100: Match in multiple sources

Return ONLY this exact JSON structure, no other text:
{{
  "suspicion_score": <integer 0-100>,
  "confidence": "<low|medium|high>",
  "findings": [
    {{
      "severity": "<critical|high|medium|low|info>",
      "category": "<database_match|honeypot_detected|blacklisted|no_match>",
      "title": "<short title>",
      "description": "<what was found and why it matters>",
      "evidence": "<which address matched which database>",
      "raw_snippet": null
    }}
  ],
  "summary": "<1-2 sentence cross-reference summary>",
  "insufficient_data": <true if no databases could be checked, else false>
}}"""


class CrossReferenceAgent(BaseAgent):
    agent_name = "cross_reference"

    async def run(
        self,
        scam_results: list[ToolResult],
        addresses_checked: list[str],
    ) -> AgentFindings:
        try:
            if not scam_results:
                return AgentFindings.insufficient(
                    self.agent_name, "No cross-reference results available"
                )

            xref_summary = []
            for result in scam_results:
                if result.data:
                    xref_summary.append({
                        "address": result.data.get("address", ""),
                        "matched": result.data.get("matched", False),
                        "confidence": result.data.get("confidence", "none"),
                        "match_sources": result.data.get("match_sources", []),
                        "csv_match": result.data.get("csv_match", False),
                        "goplus_flagged": result.data.get("goplus_flagged", False),
                        "goplus_details": result.data.get("goplus_details"),
                    })

            prompt = CROSSREF_PROMPT.format(
                addresses=", ".join(addresses_checked),
                xref_data=json.dumps(xref_summary, indent=2),
            )

            raw = await self._call_llm(prompt)
            return self._parse_findings(raw)

        except Exception as e:
            return AgentFindings.insufficient(self.agent_name, str(e))
