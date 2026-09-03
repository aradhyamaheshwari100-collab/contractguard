import { InvestigationState } from "./state.js";
import {
  THRESHOLD_ESCALATE_HISTORY,
  THRESHOLD_ESCALATE_CROSSREF,
  MAX_DEPTH,
  scoreToVerdict,
} from "./thresholds.js";
import { fetchContractSource, fetchWalletHistory } from "../tools/etherscan.js";
import { checkOwnershipStatus } from "../tools/web3.js";
import { checkLiquidityLock } from "../tools/dex.js";
import { searchKnownScamLists } from "../tools/scamLists.js";
import { CodeAnalysisAgent } from "../agents/codeAnalysis.js";
import { OnChainHistoryAgent } from "../agents/history.js";
import { CrossReferenceAgent } from "../agents/crossReference.js";
import { ReportSynthesisAgent } from "../agents/synthesis.js";
import { FinalReport, Finding, FindingSeverity, KeyFinding, ToolResult } from "../types.js";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function runInvestigation(state: InvestigationState): Promise<void> {
  try {
    await phase1CodeAnalysis(state);
    await sleep(200);
    await phase2History(state);
    await sleep(200);
    await phase3CrossReference(state);
    await sleep(200);
    await phase4Synthesis(state);
  } catch (err: any) {
    console.error(`Investigation ${state.jobId} encountered an error:`, err);
    state.markFailed(err.message || String(err));
  }
}

// ── Phase 1: Source Fetch & Code Analysis ─────────────────────────────────────
async function phase1CodeAnalysis(state: InvestigationState): Promise<void> {
  state.traceDecision(
    "Starting investigation. Phase 1: fetch contract source and run code analysis.",
    "start"
  );
  await sleep(150);

  const sourceResult = await fetchContractSource(state.address, state.chain);
  state.storeToolResult(sourceResult, "source_result");
  state.traceToolCall(
    "fetch_contract_source",
    `address=${state.address}, chain=${state.chain}`,
    sourceResult,
    "source_result"
  );
  await sleep(150);

  // Ownership verification check
  const ownership = await checkOwnershipStatus(state.address);
  state.storeToolResult(ownership, "ownership_result");
  state.traceToolCall(
    "check_ownership_status",
    `address=${state.address}`,
    ownership,
    "ownership_result"
  );
  await sleep(150);

  const scoreBefore = state.suspicionScore;
  const agent = new CodeAnalysisAgent();
  const findings = await agent.run(sourceResult, ownership);
  state.updateSuspicion(findings.suspicion_score);
  state.storeAgentFindings(findings);
  state.traceAgent("code_analysis", findings, scoreBefore);
  await sleep(150);

  state.traceThreshold(
    `Code analysis complete. Score: ${state.suspicionScore}/100. Threshold for history escalation: ${THRESHOLD_ESCALATE_HISTORY}.`,
    THRESHOLD_ESCALATE_HISTORY,
    state.suspicionScore
  );
}

// ── Phase 2: On-Chain History Analysis ───────────────────────────────────────
async function phase2History(state: InvestigationState): Promise<void> {
  if (state.suspicionScore < THRESHOLD_ESCALATE_HISTORY) {
    state.traceDecision(
      `Score ${state.suspicionScore} < ${THRESHOLD_ESCALATE_HISTORY}. History investigation not warranted. Proceeding to synthesis.`,
      "skip_phase_2"
    );
    return;
  }

  if (state.depth >= MAX_DEPTH) {
    state.traceDecision(
      `Max depth (${MAX_DEPTH}) reached. Skipping further escalation.`,
      "depth_guard"
    );
    return;
  }

  state.depth += 1;
  const sourceData = state.toolResults.get("source_result")?.data;
  const deployer = sourceData?.deployer_address || "";

  state.traceDecision(
    `Score ${state.suspicionScore} ≥ ${THRESHOLD_ESCALATE_HISTORY}. Escalating to on-chain history investigation. Deployer: ${deployer || "unknown"}`,
    "escalate_phase_2"
  );
  await sleep(150);

  let historyResult: ToolResult;
  if (deployer) {
    historyResult = await fetchWalletHistory(deployer, state.chain);
  } else {
    historyResult = {
      tool: "fetch_wallet_history",
      success: false,
      insufficient_data: true,
      data: null,
      error: "Deployer address not available",
      cached: false,
      fetched_at: new Date().toISOString(),
    };
  }
  state.storeToolResult(historyResult, "history_result");
  state.traceToolCall(
    "fetch_wallet_history",
    `deployer=${deployer}, chain=${state.chain}`,
    historyResult,
    "history_result"
  );
  await sleep(150);

  const scoreBefore = state.suspicionScore;
  const agent = new OnChainHistoryAgent();
  const findings = await agent.run(historyResult, deployer);
  state.updateSuspicion(findings.suspicion_score);
  state.storeAgentFindings(findings);
  state.traceAgent("history", findings, scoreBefore);
  await sleep(150);

  // Liquidity check
  const liqResult = await checkLiquidityLock(state.address, state.chain);
  state.storeToolResult(liqResult, "liquidity_result");
  state.traceToolCall(
    "check_liquidity_lock",
    `address=${state.address}, chain=${state.chain}`,
    liqResult,
    "liquidity_result"
  );
  await sleep(150);

  state.traceThreshold(
    `History analysis complete. Score: ${state.suspicionScore}/100. Threshold for cross-reference escalation: ${THRESHOLD_ESCALATE_CROSSREF}.`,
    THRESHOLD_ESCALATE_CROSSREF,
    state.suspicionScore
  );
}

// ── Phase 3: Cross-Reference Checks ───────────────────────────────────────────
async function phase3CrossReference(state: InvestigationState): Promise<void> {
  if (state.suspicionScore < THRESHOLD_ESCALATE_CROSSREF) {
    state.traceDecision(
      `Score ${state.suspicionScore} < ${THRESHOLD_ESCALATE_CROSSREF}. Cross-reference check not triggered.`,
      "skip_phase_3"
    );
    return;
  }

  if (state.depth >= MAX_DEPTH) {
    state.traceDecision(
      `Max depth (${MAX_DEPTH}) reached. Skipping cross-reference.`,
      "depth_guard"
    );
    return;
  }

  state.depth += 1;
  const sourceData = state.toolResults.get("source_result")?.data;
  const deployer = sourceData?.deployer_address || "";

  state.traceDecision(
    `Score ${state.suspicionScore} ≥ ${THRESHOLD_ESCALATE_CROSSREF}. Escalating to cross-reference check against known scam lists.`,
    "escalate_phase_3"
  );
  await sleep(150);

  const addressesToCheck = Array.from(new Set([state.address, deployer].filter(Boolean)));
  const xrefResults: ToolResult[] = [];

  for (const addr of addressesToCheck) {
    const res = await searchKnownScamLists(addr);
    state.storeToolResult(res, `scam_check_${addr.slice(0, 8)}`);
    state.traceToolCall(
      "search_known_scam_lists",
      `address=${addr}`,
      res,
      `scam_check_${addr.slice(0, 8)}`
    );
    xrefResults.push(res);
    await sleep(100);
  }

  const scoreBefore = state.suspicionScore;
  const agent = new CrossReferenceAgent();
  const findings = await agent.run(xrefResults, addressesToCheck);
  state.updateSuspicion(findings.suspicion_score);
  state.storeAgentFindings(findings);
  state.traceAgent("cross_reference", findings, scoreBefore);
  await sleep(150);
}

// ── Phase 4: Report Synthesis ────────────────────────────────────────────────
async function phase4Synthesis(state: InvestigationState): Promise<void> {
  state.traceDecision(
    `All investigation phases complete. Final score: ${state.suspicionScore}/100. Invoking Report Synthesis Agent.`,
    "start_synthesis"
  );
  await sleep(150);

  const scoreBefore = state.suspicionScore;
  const agent = new ReportSynthesisAgent();
  const findings = await agent.run(state);
  state.storeAgentFindings(findings);
  state.traceAgent("synthesis", findings, scoreBefore);
  await sleep(150);

  const { verdict, label: verdictLabel } = scoreToVerdict(state.suspicionScore);

  const allRawFindings: Finding[] = [];
  for (const af of state.agentFindings.values()) {
    for (const f of af.findings) {
      allRawFindings.push({ ...f, agent: af.agent });
    }
  }

  const severityOrder = [
    FindingSeverity.CRITICAL,
    FindingSeverity.HIGH,
    FindingSeverity.MEDIUM,
    FindingSeverity.LOW,
    FindingSeverity.INFO,
  ];

  allRawFindings.sort(
    (a, b) => severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity)
  );

  const keyFindings: KeyFinding[] = allRawFindings.slice(0, 5).map((f) => ({
    severity: f.severity,
    title: f.title,
    agent: f.agent,
  }));

  const report: FinalReport = {
    job_id: state.jobId,
    address: state.address,
    chain: state.chain,
    verdict,
    verdict_label: verdictLabel,
    overall_suspicion_score: state.suspicionScore,
    confidence: findings.confidence,
    investigation_depth: state.depth,
    agents_invoked: [...state.agentsInvoked],
    key_findings: keyFindings,
    all_findings: allRawFindings,
    reasoning_trail: findings.summary,
    trace: [...state.trace],
    insufficient_data_flags: [...state.insufficientDataFlags],
    generated_at: new Date().toISOString(),
  };

  state.finalise(report);
  state.traceTermination(
    `Investigation complete. Verdict: ${verdictLabel} (${state.suspicionScore}/100). Agents invoked: ${state.agentsInvoked.join(", ")}.`
  );
}
