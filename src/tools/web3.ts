import { ToolResult } from "../types.js";
import { settings } from "../config.js";

const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000";

export async function checkOwnershipStatus(contractAddress: string): Promise<ToolResult> {
  const normAddress = contractAddress.toLowerCase();

  // Demo contract overrides
  if (normAddress === "0x1111111111111111111111111111111111111111") {
    return {
      tool: "check_ownership_status",
      success: true,
      insufficient_data: false,
      data: {
        contract_address: contractAddress,
        owner: ZERO_ADDRESS,
        is_renounced: true,
        renouncement_note: "Ownership renounced — owner is zero address (0x000...)",
      },
      error: null,
      cached: false,
      fetched_at: new Date().toISOString(),
    };
  }

  if (normAddress === "0x2222222222222222222222222222222222222222") {
    const owner = "0x45fac5422f6b35d2a935b5b523a50be4e3fd3a41";
    return {
      tool: "check_ownership_status",
      success: true,
      insufficient_data: false,
      data: {
        contract_address: contractAddress,
        owner,
        is_renounced: false,
        renouncement_note: `Active owner: ${owner} (Not renounced)`,
      },
      error: null,
      cached: false,
      fetched_at: new Date().toISOString(),
    };
  }

  // Live RPC call via JSON-RPC eth_call with owner() selector 0x8da5cb5b
  if (settings.web3ProviderUrl) {
    try {
      const res = await fetch(settings.web3ProviderUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          method: "eth_call",
          params: [
            {
              to: contractAddress,
              data: "0x8da5cb5b", // bytes4(keccak256("owner()"))
            },
            "latest",
          ],
        }),
        signal: AbortSignal.timeout(5000),
      });

      if (res.ok) {
        const json = await res.json();
        if (json.result && json.result.length >= 66) {
          const rawOwner = "0x" + json.result.slice(-40);
          const isRenounced = rawOwner.toLowerCase() === ZERO_ADDRESS;
          return {
            tool: "check_ownership_status",
            success: true,
            insufficient_data: false,
            data: {
              contract_address: contractAddress,
              owner: rawOwner,
              is_renounced: isRenounced,
              renouncement_note: isRenounced
                ? "Ownership renounced — owner is zero address"
                : `Active owner: ${rawOwner}`,
            },
            error: null,
            cached: false,
            fetched_at: new Date().toISOString(),
          };
        }
      }
    } catch {
      // Fallback
    }
  }

  return {
    tool: "check_ownership_status",
    success: false,
    insufficient_data: true,
    data: null,
    error: "Contract does not implement Ownable or live RPC call failed.",
    cached: false,
    fetched_at: new Date().toISOString(),
  };
}
