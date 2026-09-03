import { BaseAgent } from "./base.js";
import { AgentFindings, ToolResult } from "../types.js";

const HISTORY_PROMPT = `You are a blockchain forensics analyst at ContractGuard. You are investigating the transaction history of a smart contract deployer wallet.

Your task: Analyze the deployer's on-chain activity for patterns consistent with scam/rug-pull behavior.

LOOK FOR THESE SUSPICIOUS PATTERNS:
1. [CRITICAL] Multiple contract deployments in a short time window (serial scammer pattern)
2. [CRITICAL] Prior contracts that were abandoned after initial liquidity was added
3. [HIGH] Large ETH/token withdrawals from contracts shortly after launch
4. [HIGH] Deployer receiving funds from known mixer addresses (Tornado Cash patterns)
5. [HIGH] Very new wallet with minimal history suddenly deploying contracts
6. [MEDIUM] Deployer has deployed 5+ contracts across different names/symbols

SCORING GUIDANCE:
- 0-30: Normal wallet behavior, no red flags
- 31-60: Some unusual patterns
- 61-80: Multiple concerning patterns, likely serial deployer
- 81-100: Strong evidence of prior scam activity

Return ONLY this exact JSON structure:
{
  "suspicion_score": <integer 0-100>,
  "confidence": "<low|medium|high>",
  "findings": [
    {
      "severity": "<critical|high|medium|low|info>",
      "category": "<serial_deployer|prior_rug|mixer_links|fresh_wallet|factory_scammer|other>",
      "title": "<short title>",
      "description": "<detailed explanation with specific transaction data referenced>",
      "evidence": "<specific tx hashes, addresses, or counts that support this finding>",
      "raw_snippet": null
    }
  ],
  "summary": "<1-2 sentence summary of deployer risk profile>",
  "insufficient_data": <true if tx data is empty or unavailable, else false>
}`;

export class OnChainHistoryAgent extends BaseAgent {
  agentName = "history";

  async run(historyResult: ToolResult, deployer: string = ""): Promise<AgentFindings> {
    if (historyResult.insufficient_data || !historyResult.data) {
      return {
        agent: this.agentName,
        suspicion_score: 50,
        confidence: "low",
        findings: [],
        summary: `Transaction history unavailable for deployer ${deployer || "unknown"}.`,
        insufficient_data: true,
      };
    }

    const data = historyResult.data;
    const txs = Array.isArray(data.transactions) ? data.transactions : [];

    try {
      const prompt = `${HISTORY_PROMPT}

DEPLOYER ADDRESS: ${deployer || "Unknown"}
TOTAL TRANSACTIONS: ${data.transaction_count || 0}
CONTRACT DEPLOYMENTS BY THIS WALLET: ${data.deployment_count || 0}
DEPLOYED CONTRACT ADDRESSES: ${(data.deployed_contracts || []).slice(0, 10).join(", ")}

RECENT TRANSACTIONS:
${JSON.stringify(txs.slice(0, 30), null, 2)}
`;
      const raw = await this.callLLM(prompt);
      return this.parseFindings(raw);
    } catch {
      return this.heuristicAnalysis(data, deployer);
    }
  }

  private heuristicAnalysis(data: Record<string, any>, deployer: string): AgentFindings {
    const deploymentCount = Number(data.deployment_count || 0);
    const txs = Array.isArray(data.transactions) ? data.transactions : [];

    const hasMixer = txs.some(
      (tx: any) =>
        String(tx.from).toLowerCase() === "0x7db418b5d567a4e0e8c59ad71be1fce48f3e6107" ||
        String(tx.to).toLowerCase() === "0x7db418b5d567a4e0e8c59ad71be1fce48f3e6107"
    );

    if (deploymentCount >= 3 || hasMixer) {
      const findings: any[] = [];
      if (deploymentCount >= 3) {
        findings.push({
          severity: "critical",
          category: "serial_deployer",
          title: "Serial Rug-Pull Deployer Pattern",
          description: `Wallet has deployed ${deploymentCount} distinct contracts within a short duration.`,
          evidence: `${deploymentCount} contract deployments recorded`,
        });
      }
      if (hasMixer) {
        findings.push({
          severity: "high",
          category: "mixer_links",
          title: "Funding Received from Known Mixer",
          description: "Deployer wallet received incoming seed transactions linked to privacy mixer contracts (Tornado Cash).",
          evidence: "Inbound transaction from 0x7db4...6107",
        });
      }
      return this.parseFindings({
        suspicion_score: 90,
        confidence: "high",
        findings,
        summary: `Deployer wallet ${deployer} demonstrates high-risk forensics: serial contract deployment behavior and mixer association.`,
        insufficient_data: false,
      });
    }

    return this.parseFindings({
      suspicion_score: 20,
      confidence: "medium",
      findings: [],
      summary: `Deployer transaction history appears within normal parameters.`,
      insufficient_data: false,
    });
  }
}
