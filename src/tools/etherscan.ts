import fs from "fs";
import path from "path";
import { ToolResult } from "../types.js";
import { settings } from "../config.js";

const CHAIN_URLS: Record<string, string> = {
  mainnet: "https://api.etherscan.io/api",
  sepolia: "https://api-sepolia.etherscan.io/api",
  polygon: "https://api.polygonscan.com/api",
  polygon_amoy: "https://api-amoy.polygonscan.com/api",
};

const memoryCache = new Map<string, { value: any; expiresAt: number }>();

function getCached(key: string): any | null {
  const item = memoryCache.get(key);
  if (!item) return null;
  if (Date.now() > item.expiresAt) {
    memoryCache.delete(key);
    return null;
  }
  return item.value;
}

function setCached(key: string, value: any, ttlSec: number = 3600): void {
  memoryCache.set(key, { value, expiresAt: Date.now() + ttlSec * 1000 });
}

function readContractFile(fileName: string): string {
  try {
    const p = path.resolve(process.cwd(), "contracts", fileName);
    if (fs.existsSync(p)) {
      return fs.readFileSync(p, "utf-8");
    }
  } catch {
    // fallback
  }
  return "";
}

export async function fetchContractSource(address: string, chain: string = "sepolia"): Promise<ToolResult> {
  const normAddress = address.toLowerCase();
  const cacheKey = `source:${chain}:${normAddress}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return {
      tool: "fetch_contract_source",
      success: true,
      insufficient_data: false,
      data: cached,
      error: null,
      cached: true,
      fetched_at: new Date().toISOString(),
    };
  }

  // Check demo contracts first
  if (normAddress === "0x1111111111111111111111111111111111111111") {
    const code = readContractFile("CleanToken.sol");
    const payload = {
      source_code: code || "// CleanToken ERC20 sample\ncontract CleanToken is ERC20, Ownable {}",
      abi: JSON.stringify([
        { type: "function", name: "owner", inputs: [], outputs: [{ type: "address" }] },
        { type: "function", name: "totalSupply", inputs: [], outputs: [{ type: "uint256" }] },
      ]),
      contract_name: "CleanToken",
      compiler_version: "v0.8.20+commit.a1b79de6",
      is_verified: true,
      deployer_address: "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
      proxy: "0",
      implementation: "",
    };
    setCached(cacheKey, payload);
    return {
      tool: "fetch_contract_source",
      success: true,
      insufficient_data: false,
      data: payload,
      error: null,
      cached: false,
      fetched_at: new Date().toISOString(),
    };
  }

  if (normAddress === "0x2222222222222222222222222222222222222222") {
    const code = readContractFile("BackdooredToken.sol");
    const payload = {
      source_code: code || "// BackdooredToken sample\ncontract BackdooredToken is ERC20, Ownable {}",
      abi: JSON.stringify([
        { type: "function", name: "emergencyWithdraw", inputs: [{ type: "address" }, { type: "uint256" }] },
        { type: "function", name: "mint", inputs: [{ type: "address" }, { type: "uint256" }] },
        { type: "function", name: "setBlacklist", inputs: [{ type: "address" }, { type: "bool" }] },
        { type: "function", name: "setTransferFee", inputs: [{ type: "uint256" }] },
      ]),
      contract_name: "BackdooredToken",
      compiler_version: "v0.8.20+commit.a1b79de6",
      is_verified: true,
      deployer_address: "0x45fac5422f6b35d2a935b5b523a50be4e3fd3a41",
      proxy: "0",
      implementation: "",
    };
    setCached(cacheKey, payload);
    return {
      tool: "fetch_contract_source",
      success: true,
      insufficient_data: false,
      data: payload,
      error: null,
      cached: false,
      fetched_at: new Date().toISOString(),
    };
  }

  // Live Etherscan query
  if (settings.etherscanApiKey) {
    try {
      const baseUrl = CHAIN_URLS[chain.toLowerCase()] || CHAIN_URLS.sepolia;
      const url = `${baseUrl}?module=contract&action=getsourcecode&address=${address}&apikey=${settings.etherscanApiKey}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (res.ok) {
        const json = await res.json();
        if (json.status === "1" && json.result && json.result.length > 0) {
          const r = json.result[0];
          const source = r.SourceCode || "";
          const isVerified = Boolean(source && source.trim());

          // Attempt to get deployer
          let deployerAddress = "";
          try {
            const createUrl = `${baseUrl}?module=contract&action=getcontractcreation&contractaddresses=${address}&apikey=${settings.etherscanApiKey}`;
            const cRes = await fetch(createUrl, { signal: AbortSignal.timeout(5000) });
            if (cRes.ok) {
              const cJson = await cRes.json();
              if (cJson.status === "1" && cJson.result && cJson.result.length > 0) {
                deployerAddress = cJson.result[0].contractCreator || "";
              }
            }
          } catch {
            // ignore
          }

          const payload = {
            source_code: isVerified ? source : "",
            abi: r.ABI || "",
            contract_name: r.ContractName || "Unknown",
            compiler_version: r.CompilerVersion || "",
            is_verified: isVerified,
            deployer_address: deployerAddress,
            proxy: r.Proxy || "0",
            implementation: r.Implementation || "",
          };
          setCached(cacheKey, payload);
          return {
            tool: "fetch_contract_source",
            success: true,
            insufficient_data: !isVerified,
            data: payload,
            error: isVerified ? null : "Contract source code is unverified on Etherscan.",
            cached: false,
            fetched_at: new Date().toISOString(),
          };
        }
      }
    } catch (err: any) {
      console.warn("Etherscan fetch error:", err);
    }
  }

  // Default fallback if no key or query failed
  return {
    tool: "fetch_contract_source",
    success: false,
    insufficient_data: true,
    data: {
      source_code: "",
      abi: "",
      contract_name: "Unverified Contract",
      compiler_version: "",
      is_verified: false,
      deployer_address: "",
    },
    error: "Contract source not verified on Etherscan or Etherscan API key not set.",
    cached: false,
    fetched_at: new Date().toISOString(),
  };
}

export async function fetchWalletHistory(address: string, chain: string = "sepolia"): Promise<ToolResult> {
  const normAddress = address.toLowerCase();
  const cacheKey = `history:${chain}:${normAddress}`;
  const cached = getCached(cacheKey);
  if (cached) {
    return {
      tool: "fetch_wallet_history",
      success: true,
      insufficient_data: false,
      data: cached,
      error: null,
      cached: true,
      fetched_at: new Date().toISOString(),
    };
  }

  // Demo address for known scam / rug puller
  if (normAddress === "0x45fac5422f6b35d2a935b5b523a50be4e3fd3a41" || normAddress === "0x2222222222222222222222222222222222222222") {
    const transactions = [
      {
        hash: "0xaa128491bb7201c38e91",
        from: address,
        to: "CONTRACT_CREATION",
        value_eth: "0.0",
        contract_created: "0x2222222222222222222222222222222222222222",
        timestamp: "1716200000",
        isError: "0",
      },
      {
        hash: "0xbb349102cc8392d49f02",
        from: address,
        to: "CONTRACT_CREATION",
        value_eth: "0.0",
        contract_created: "0x72a5343dc1b386a3e509ce39f0b5c00f67e17ba5",
        timestamp: "1716100000",
        isError: "0",
      },
      {
        hash: "0xcc560213dd9403e50a13",
        from: address,
        to: "CONTRACT_CREATION",
        value_eth: "0.0",
        contract_created: "0xbebe69e9634b73c0df8e5d924038e4e0c1af2e4a",
        timestamp: "1715900000",
        isError: "0",
      },
      {
        hash: "0xdd781324ee0514f61b24",
        from: "0x7db418b5d567a4e0e8c59ad71be1fce48f3e6107", // Tornado cash
        to: address,
        value_eth: "15.5",
        contract_created: "",
        timestamp: "1715800000",
        isError: "0",
      },
      {
        hash: "0xee902435ff1625a72c35",
        from: address,
        to: "0x000000000000000000000000000000000000dEaD",
        value_eth: "14.8",
        contract_created: "",
        timestamp: "1716210000",
        isError: "0",
      },
    ];

    const payload = {
      address,
      transaction_count: 52,
      transactions,
      deployment_count: 7,
      deployed_contracts: [
        "0x2222222222222222222222222222222222222222",
        "0x72a5343dc1b386a3e509ce39f0b5c00f67e17ba5",
        "0xbebe69e9634b73c0df8e5d924038e4e0c1af2e4a",
      ],
    };
    setCached(cacheKey, payload);
    return {
      tool: "fetch_wallet_history",
      success: true,
      insufficient_data: false,
      data: payload,
      error: null,
      cached: false,
      fetched_at: new Date().toISOString(),
    };
  }

  // Live Etherscan query
  if (settings.etherscanApiKey) {
    try {
      const baseUrl = CHAIN_URLS[chain.toLowerCase()] || CHAIN_URLS.sepolia;
      const url = `${baseUrl}?module=account&action=txlist&address=${address}&startblock=0&endblock=99999999&page=1&offset=50&sort=desc&apikey=${settings.etherscanApiKey}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (res.ok) {
        const json = await res.json();
        if (json.status === "1" && Array.isArray(json.result)) {
          const normalTxs = json.result;
          const deployments = normalTxs.filter((tx: any) => !tx.to && tx.contractAddress);
          const payload = {
            address,
            transaction_count: normalTxs.length,
            transactions: normalTxs.slice(0, 30),
            deployment_count: deployments.length,
            deployed_contracts: deployments.map((tx: any) => tx.contractAddress),
          };
          setCached(cacheKey, payload);
          return {
            tool: "fetch_wallet_history",
            success: true,
            insufficient_data: false,
            data: payload,
            error: null,
            cached: false,
            fetched_at: new Date().toISOString(),
          };
        }
      }
    } catch (err: any) {
      console.warn("Wallet history fetch error:", err);
    }
  }

  return {
    tool: "fetch_wallet_history",
    success: false,
    insufficient_data: true,
    data: null,
    error: `Transaction history unavailable for deployer ${address || "unknown"}.`,
    cached: false,
    fetched_at: new Date().toISOString(),
  };
}
