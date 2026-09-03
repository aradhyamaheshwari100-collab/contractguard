"""
agents/synthesis.py — Report Synthesis Agent.
Always the final agent. Compiles all prior findings into a coherent
narrative reasoning trail and final verdict. Never skipped.
"""
from __future__ import annotations
import json
from models import AgentFindings
from agents.base import BaseAgent

SYNTHESIS_PROMPT = """You are the final reporting analyst at ContractGuard, an AI-powered smart contract fraud detection system.

Your task: Write a clear, evidence-backed reasoning trail that explains the investigation findings and justifies the final risk verdict.

INVESTIGATION SUMMARY:
- Contract Address: {address}
- Chain: {chain}
- Final Suspicion Score: {score}/100
- Agents Invoked: {agents_invoked}
- Investigation Depth: {depth}

FINDINGS FROM ALL AGENTS:
{all_findings}

INSUFFICIENT DATA FLAGS (tools that could not provide data):
{insufficient_flags}

VERDICT BANDS:
- 0-30:   LOW RISK
- 31-69:  MEDIUM RISK
- 70-100: HIGH RISK
- (Use INSUFFICIENT_DATA if data was so limited that a confident verdict is impossible)

Write the reasoning_trail as if explaining to a non-technical user WHY this verdict was reached.
Reference specific findings by name. Be direct and clear about what was found and what it means.
If data was limited, acknowledge it and explain how that affected confidence.

Return ONLY this exact JSON structure, no other text:
{{
  "suspicion_score": {score},
  "confidence": "<low|medium|high>",
  "findings": [],
  "summary": "<3-5 sentence narrative reasoning trail that connects all evidence to the final verdict. Mention specific findings, scores, and what they mean for user safety. This will be shown verbatim in the report card.>",
  "insufficient_data": <true only if evidence was so limited no verdict is possible>
}}"""


class ReportSynthesisAgent(BaseAgent):
    agent_name = "synthesis"

    async def run(self, state: object) -> AgentFindings:  # type: ignore[override]
        try:
            # Collect all findings from state
            all_findings = []
            for agent_name, af in state.agent_findings.items():
                for f in af.findings:
                    all_findings.append({
                        "agent": agent_name,
                        "severity": f.severity.value,
                        "title": f.title,
                        "description": f.description,
                        "evidence": f.evidence,
                    })

            prompt = SYNTHESIS_PROMPT.format(
                address=state.address,
                chain=state.chain,
                score=state.suspicion_score,
                agents_invoked=", ".join(state.agents_invoked),
                depth=state.depth,
                all_findings=json.dumps(all_findings, indent=2)[:5000],
                insufficient_flags=(
                    ", ".join(state.insufficient_data_flags)
                    if state.insufficient_data_flags else "None"
                ),
            )

            raw = await self._call_llm(prompt)
            # Ensure score is preserved from state (synthesis doesn't change the score)
            raw["suspicion_score"] = state.suspicion_score
            return self._parse_findings(raw)

        except Exception as e:
            # Synthesis must never completely fail — build a minimal report
            return AgentFindings(
                agent=self.agent_name,
                suspicion_score=state.suspicion_score,
                confidence="low",
                findings=[],
                summary=(
                    f"Report synthesis encountered an error: {e}. "
                    f"Raw score: {state.suspicion_score}/100. "
                    f"Agents completed: {', '.join(state.agents_invoked)}."
                ),
                insufficient_data=False,
            )
