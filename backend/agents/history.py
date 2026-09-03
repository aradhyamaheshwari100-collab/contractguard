"""
agents/history.py — On-Chain History Agent.
Investigates the deployer wallet's transaction history for
suspicious behavioral patterns (prior rug pulls, rapid deployments,
liquidity drain signatures, etc.).
Only invoked when code analysis suspicion score ≥ threshold.
"""
from __future__ import annotations
from models import AgentFindings, ToolResult
from agents.base import BaseAgent

HISTORY_PROMPT = """You are a blockchain forensics analyst at ContractGuard. You are investigating the transaction history of a smart contract deployer wallet.

Your task: Analyze the deployer's on-chain activity for patterns consistent with scam/rug-pull behavior.

LOOK FOR THESE SUSPICIOUS PATTERNS:
1. [CRITICAL] Multiple contract deployments in a short time window (serial scammer pattern)
2. [CRITICAL] Prior contracts that were abandoned after initial liquidity was added (classic rug)
3. [HIGH] Large ETH/token withdrawals from contracts shortly after launch
4. [HIGH] Deployer receiving funds from known mixer addresses (Tornado Cash patterns)
5. [HIGH] Very new wallet with minimal history but suddenly deploying contracts
6. [MEDIUM] Deployer has deployed 5+ contracts across different names/symbols (factory scammer)
7. [MEDIUM] Transactions with very high gas prices suggesting front-running awareness
8. [LOW] Wallet balance currently near-zero (funds moved after previous operations)

DEPLOYER ADDRESS: {deployer}
TOTAL TRANSACTIONS: {tx_count}
CONTRACT DEPLOYMENTS BY THIS WALLET: {deployment_count}
DEPLOYED CONTRACT ADDRESSES: {deployed_contracts}

RECENT TRANSACTION DATA (last 50 transactions):
{tx_data}

SCORING GUIDANCE:
- 0-30:  Normal wallet behavior, no red flags
- 31-60: Some unusual patterns, worth noting
- 61-80: Multiple concerning patterns, likely serial deployer
- 81-100: Strong evidence of prior scam activity

Return ONLY this exact JSON structure, no other text:
{{
  "suspicion_score": <integer 0-100>,
  "confidence": "<low|medium|high>",
  "findings": [
    {{
      "severity": "<critical|high|medium|low|info>",
      "category": "<serial_deployer|prior_rug|mixer_links|fresh_wallet|factory_scammer|other>",
      "title": "<short title>",
      "description": "<detailed explanation with specific transaction data referenced>",
      "evidence": "<specific tx hashes, addresses, or counts that support this finding>",
      "raw_snippet": null
    }}
  ],
  "summary": "<1-2 sentence summary of deployer risk profile>",
  "insufficient_data": <true if tx data is empty or unavailable, else false>
}}"""


class OnChainHistoryAgent(BaseAgent):
    agent_name = "history"

    async def run(
        self,
        history_result: ToolResult,
        deployer: str = "",
    ) -> AgentFindings:
        try:
            if history_result.insufficient_data or not history_result.data:
                return AgentFindings.insufficient(
                    self.agent_name,
                    f"Transaction history unavailable for deployer {deployer or 'unknown'}"
                )

            data = history_result.data
            txs = data.get("transactions", [])

            # Format tx data for LLM (limit to relevant fields to stay within context)
            tx_summary = []
            for tx in txs[:30]:  # Top 30 most recent
                tx_summary.append({
                    "hash": tx.get("hash", "")[:20] + "...",
                    "from": tx.get("from", ""),
                    "to": tx.get("to", "") or "CONTRACT_CREATION",
                    "value_eth": str(int(tx.get("value", "0")) / 1e18)[:8],
                    "contract_created": tx.get("contractAddress", ""),
                    "timestamp": tx.get("timeStamp", ""),
                    "isError": tx.get("isError", "0"),
                })

            import json
            prompt = HISTORY_PROMPT.format(
                deployer=deployer or "Unknown",
                tx_count=data.get("transaction_count", 0),
                deployment_count=data.get("deployment_count", 0),
                deployed_contracts=", ".join(data.get("deployed_contracts", [])[:10]),
                tx_data=json.dumps(tx_summary, indent=2)[:4000],
            )

            raw = await self._call_llm(prompt)
            return self._parse_findings(raw)

        except Exception as e:
            return AgentFindings.insufficient(self.agent_name, str(e))
