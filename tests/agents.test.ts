import test from "node:test";
import assert from "node:assert";
import { CodeAnalysisAgent } from "../src/agents/codeAnalysis.js";

test("CodeAnalysisAgent - heuristic fallback for backdoored contract", async (t) => {
  const agent = new CodeAnalysisAgent();
  
  const mockSourceResult = {
    tool: "fetch_contract_source",
    success: true,
    insufficient_data: false,
    data: {
      source_code: "function emergencyWithdraw(address to, uint256 amount) external onlyOwner { _transfer(address(this), to, amount); }",
      abi: "",
      contract_name: "BackdooredToken",
      is_verified: true,
    },
    error: null,
    cached: true,
    fetched_at: new Date().toISOString()
  };

  // Set GEMINI_API_KEY to empty to force heuristic fallback if it checks for it, 
  // or it might just fail the LLM call and fallback.
  // Actually, we can test it directly if we mock the LLM or if the LLM call fails due to invalid key.
  
  // Since we don't have a mock for callLLM right now, let's assume it will fall back 
  // if no valid key is present, or we can just test the public `heuristicAnalysis` via `any` type workaround 
  // but it's private. Let's just run it and if it uses heuristic it will work.
  const originalKey = process.env.GEMINI_API_KEY;
  process.env.GEMINI_API_KEY = "invalid_key_for_test"; // Force LLM to fail and use fallback
  
  try {
    const findings = await agent.run(mockSourceResult);
    
    assert.strictEqual(findings.suspicion_score, 85, "Should score 85 for backdoor heuristic");
    assert.ok(findings.findings.some(f => f.category === "owner_drain"), "Should find owner_drain");
  } finally {
    process.env.GEMINI_API_KEY = originalKey;
  }
});
