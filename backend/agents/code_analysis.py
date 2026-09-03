"""
agents/code_analysis.py — Code Analysis Agent.
Always the first agent to run. Analyzes verified Solidity source code
(or ABI if source is unavailable) for common fraud/scam patterns.
"""
from __future__ import annotations
from typing import Optional
from models import AgentFindings, ToolResult
from agents.base import BaseAgent

ANALYSIS_PROMPT = """You are an expert Solidity smart contract security auditor working for ContractGuard, an autonomous fraud detection system.

Your task: Analyze the provided smart contract and identify fraud or rug-pull risk patterns.

LOOK FOR THESE SPECIFIC PATTERNS (assign severity as shown):
1. [CRITICAL] Owner-drain functions: functions that allow the owner to transfer user tokens/ETH to arbitrary addresses (e.g., emergencyWithdraw, rescueTokens, sweep, skim)
2. [CRITICAL] Unlimited mint: mint functions callable by owner with no supply ceiling or only-owner restriction
3. [HIGH] Transfer blacklisting: functions that can block specific addresses from transferring tokens
4. [HIGH] Hidden fees: transfer tax or fee mechanisms that can be raised to 100% by the owner
5. [HIGH] Missing ownership renouncement: owner is not the zero address and no renouncement mechanism exists
6. [HIGH] Proxy upgradeable with no timelock: contract can be silently upgraded by a central party
7. [MEDIUM] Pausable transfers: owner can pause all transfers indefinitely
8. [MEDIUM] Centralized price oracle: price feeds controlled by a single owner address
9. [LOW] Missing events on critical state changes
10. [LOW] Reentrancy guard absent on fund-moving functions

SCORING GUIDANCE:
- 0-20:  No significant risk patterns found
- 21-40: Minor concerns, standard patterns
- 41-69: Moderate risk, some concerning patterns
- 70-85: High risk, multiple serious patterns found
- 86-100: Critical risk, clear fraud indicators present

CONTRACT SOURCE CODE:
{source_code}

ABI (if source unavailable):
{abi}

CONTRACT NAME: {contract_name}
IS VERIFIED: {is_verified}
OWNERSHIP STATUS: {ownership_info}

Return ONLY this exact JSON structure, no other text:
{{
  "suspicion_score": <integer 0-100>,
  "confidence": "<low|medium|high>",
  "findings": [
    {{
      "severity": "<critical|high|medium|low|info>",
      "category": "<owner_drain|unlimited_mint|blacklisting|hidden_fees|no_renouncement|proxy_risk|pausable|other>",
      "title": "<short title>",
      "description": "<detailed explanation of why this is risky>",
      "evidence": "<where in the code: line numbers or function names>",
      "raw_snippet": "<exact code snippet if available, else null>"
    }}
  ],
  "summary": "<1-2 sentence summary of findings and recommended next steps>",
  "insufficient_data": <true if source and ABI both unavailable, else false>
}}"""


class CodeAnalysisAgent(BaseAgent):
    agent_name = "code_analysis"

    async def run(
        self,
        source_result: ToolResult,
        ownership_result: Optional[ToolResult] = None,
    ) -> AgentFindings:
        try:
            data = source_result.data or {}
            source_code = data.get("source_code", "")
            abi = data.get("abi", "")
            contract_name = data.get("contract_name", "Unknown")
            is_verified = data.get("is_verified", False)

            if not source_code and not abi:
                return AgentFindings.insufficient(
                    self.agent_name,
                    "Neither source code nor ABI is available for this contract."
                )

            ownership_info = "Unknown"
            if ownership_result and ownership_result.data:
                od = ownership_result.data
                ownership_info = (
                    f"Owner: {od.get('owner', 'N/A')} | "
                    f"Renounced: {od.get('is_renounced', False)}"
                )

            prompt = ANALYSIS_PROMPT.format(
                source_code=source_code[:8000] if source_code else "NOT AVAILABLE",
                abi=abi[:2000] if abi else "NOT AVAILABLE",
                contract_name=contract_name,
                is_verified=is_verified,
                ownership_info=ownership_info,
            )

            raw = await self._call_llm(prompt)
            return self._parse_findings(raw)

        except Exception as e:
            return AgentFindings.insufficient(self.agent_name, str(e))
