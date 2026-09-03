import test from "node:test";
import assert from "node:assert";
import { fetchContractSource } from "../src/tools/etherscan.js";
import { checkOwnershipStatus } from "../src/tools/web3.js";

test("etherscan tool - demo clean address", async (t) => {
  const address = "0x1111111111111111111111111111111111111111";
  
  const result = await fetchContractSource(address, "sepolia");
  
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.data.contract_name, "CleanToken");
  assert.strictEqual(result.data.is_verified, true);
});

test("etherscan tool - demo backdoored address", async (t) => {
  const address = "0x2222222222222222222222222222222222222222";
  
  const result = await fetchContractSource(address, "sepolia");
  
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.data.contract_name, "BackdooredToken");
  assert.strictEqual(result.data.is_verified, true);
});

test("web3 tool - ownership status", async (t) => {
  const address = "0x1111111111111111111111111111111111111111";
  const result = await checkOwnershipStatus(address);
  
  assert.strictEqual(result.success, true);
  // Web3 tool for demo addresses currently returns success and uses fallback behavior or specific demo behavior
  assert.ok(result.data !== undefined);
});
