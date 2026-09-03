import { BaseAgent } from "./base.js";
import { AgentFindings, ToolResult } from "../types.js";

const CROSSREF_PROMPT = `You are a threat intelligence analyst at ContractGuard.

Your task: Evaluate the results of cross-referencing addresses against known scam/fraud databases and determine the implications.

ADDRESSES CHECKED: {addresses}

CROSS-REFERENCE RESULTS:
{xref_data}

DATABASE SOURCES CHECKED:
- CryptoScamDB static list (community-reported scam addresses)
- GoPlus Security API (if available)

SCORING GUIDANCE:
- 0: No matches found in any database
- 40-60: Match in lower-confidence source
- 70-85: Match in high-confidence source (CryptoScamDB)
- 86-100: Match in multiple sources or confirmed honeypot

Return ONLY this exact JSON structure:
{
  "suspicion_score": <integer 0-100>,
  "confidence": "<low|medium|high>",
  "findings": [
    {
      "severity": "<critical|high|medium|low|info>",
      "category": "<database_match|honeypot_detected|blacklisted|no_match>",
      "title": "<short title>",
      "description": "<what was found and why it matters>",
      "evidence": "<which address matched which database>",
      "raw_snippet": null
    }
  ],
  "summary": "<1-2 sentence cross-reference summary>",
  "insufficient_data": <true if no databases could be checked, else false>
}`;

export class CrossReferenceAgent extends BaseAgent {
  agentName = "cross_reference";

  async run(scamResults: ToolResult[], addressesChecked: string[]): Promise<AgentFindings> {
    if (!scamResults || scamResults.length === 0) {
      return {
        agent: this.agentName,
        suspicion_score: 50,
        confidence: "low",
        findings: [],
        summary: "No cross-reference results available.",
        insufficient_data: true,
      };
    }

    const xrefSummary = scamResults.map((r) => ({
      address: r.data?.address || "",
      matched: Boolean(r.data?.matched),
      confidence: r.data?.confidence || "none",
      match_sources: r.data?.match_sources || [],
      csv_match: Boolean(r.data?.csv_match),
      goplus_flagged: Boolean(r.data?.goplus_flagged),
    }));

    try {
      const prompt = CROSSREF_PROMPT.replace("{addresses}", addressesChecked.join(", ")).replace(
        "{xref_data}",
        JSON.stringify(xrefSummary, null, 2)
      );
      const raw = await this.callLLM(prompt);
      return this.parseFindings(raw);
    } catch {
      return this.heuristicAnalysis(xrefSummary);
    }
  }

  private heuristicAnalysis(xrefSummary: any[]): AgentFindings {
    const matchedItems = xrefSummary.filter((x) => x.matched);

    if (matchedItems.length > 0) {
      const findings = matchedItems.map((item) => ({
        severity: "critical",
        category: "database_match",
        title: "Confirmed Scam Entity Match",
        description: `Address ${item.address} is indexed in the security blacklist (${item.match_sources.join(", ")}).`,
        evidence: `Sources: ${item.match_sources.join(", ")}`,
      }));

      return this.parseFindings({
        suspicion_score: 95,
        confidence: "high",
        findings,
        summary: `Address matched confirmed scam intelligence records in CryptoScamDB.`,
        insufficient_data: false,
      });
    }

    return this.parseFindings({
      suspicion_score: 0,
      confidence: "high",
      findings: [],
      summary: "No matched entries found across scam threat databases.",
      insufficient_data: false,
    });
  }
}
