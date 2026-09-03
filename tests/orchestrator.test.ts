import test from "node:test";
import assert from "node:assert";
import { runInvestigation } from "../src/orchestrator/loop.js";
import { InvestigationState } from "../src/orchestrator/state.js";
import { Verdict } from "../src/types.js";

test("orchestrator - end-to-end clean address (0x1111...)", async (t) => {
  const address = "0x1111111111111111111111111111111111111111";
  const jobId = "test-job-clean";
  const state = new InvestigationState(jobId, address, "sepolia");
  
  await runInvestigation(state);
  
  const report = state.report;
  assert.ok(report, "Report should be generated");
  
  // Clean address should be SAFE or at most NEUTRAL, but let's assert it doesn't get marked MALICIOUS
  assert.notStrictEqual(report.verdict, Verdict.MALICIOUS, "Verdict should not be MALICIOUS for clean demo address");
  
  // Assert agents invoked
  assert.ok(report.agents_invoked.includes("code_analysis"));
  assert.ok(report.agents_invoked.includes("synthesis"));
  
  // Assert trace decisions
  const decisionTraces = report.trace.filter(t => t.type === 'decision');
  assert.ok(decisionTraces.length > 0, "Should have decision traces");
});

test("orchestrator - end-to-end backdoored address (0x2222...)", async (t) => {
  const address = "0x2222222222222222222222222222222222222222";
  const jobId = "test-job-backdoor";
  const state = new InvestigationState(jobId, address, "sepolia");
  
  await runInvestigation(state);
  
  const report = state.report;
  assert.ok(report, "Report should be generated");
  
  // Backdoored address should escalate
  assert.ok(
    report.verdict === Verdict.MALICIOUS || report.verdict === Verdict.SUSPICIOUS,
    "Verdict should be MALICIOUS or SUSPICIOUS for backdoored demo address"
  );
  
  // Assert agents invoked
  assert.ok(report.agents_invoked.includes("code_analysis"));
  assert.ok(report.agents_invoked.includes("history"));
  // cross_reference might be invoked depending on the score, but history definitely should be.
  assert.ok(report.agents_invoked.includes("synthesis"));
  
  // Assert investigation depth
  assert.ok(report.investigation_depth >= 1, "Depth should be at least 1 due to escalation");
  
  // Assert trace decisions
  const decisionTraces = report.trace.filter(t => t.type === 'decision');
  assert.ok(decisionTraces.length > 0, "Should have decision traces");
});
