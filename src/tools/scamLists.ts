import fs from "fs";
import path from "path";
import { ToolResult } from "../types.js";
import { settings } from "../config.js";

let cachedScamAddresses: Set<string> | null = null;

function loadScamAddresses(): Set<string> {
  if (cachedScamAddresses) {
    return cachedScamAddresses;
  }
  const set = new Set<string>();
  try {
    const csvPath = path.resolve(process.cwd(), "data", "known_scams.csv");
    if (fs.existsSync(csvPath)) {
      const content = fs.readFileSync(csvPath, "utf-8");
      const lines = content.split("\n");
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        const parts = line.split(",");
        const addr = parts[0]?.trim().toLowerCase();
        if (addr && addr.startsWith("0x") && addr.length === 42) {
          set.add(addr);
        }
      }
    }
  } catch (err) {
    console.warn("Failed to read known_scams.csv:", err);
  }
  cachedScamAddresses = set;
  return set;
}

async function checkGoPlus(address: string): Promise<Record<string, any> | null> {
  if (!settings.goplusApiKey) return null;
  try {
    const res = await fetch(`https://api.gopluslabs.io/api/v1/token_security/1?contract_addresses=${address}`, {
      headers: { Authorization: settings.goplusApiKey },
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const data = await res.json();
      return data?.result?.[address.toLowerCase()] || null;
    }
  } catch {
    // Graceful fallback
  }
  return null;
}

export async function searchKnownScamLists(address: string): Promise<ToolResult> {
  const addrLower = address.toLowerCase();
  const knownScams = loadScamAddresses();
  const csvMatch = knownScams.has(addrLower);

  const goplusResult = await checkGoPlus(address);
  let goplusFlagged = false;
  let goplusDetails: Record<string, any> | null = null;

  if (goplusResult) {
    goplusFlagged = goplusResult.is_honeypot === "1" || goplusResult.is_blacklisted === "1";
    goplusDetails = {
      is_honeypot: goplusResult.is_honeypot,
      is_blacklisted: goplusResult.is_blacklisted,
      cannot_sell_all: goplusResult.cannot_sell_all,
    };
  }

  const matched = csvMatch || goplusFlagged;
  const sources: string[] = [];
  if (csvMatch) sources.push("CryptoScamDB static list");
  if (goplusFlagged) sources.push("GoPlus Security API");

  let confidence: "none" | "low" | "medium" | "high" = "none";
  if (sources.length > 1 || csvMatch) {
    confidence = "high";
  } else if (goplusFlagged) {
    confidence = "medium";
  }

  return {
    tool: "search_known_scam_lists",
    success: true,
    insufficient_data: false,
    data: {
      address,
      matched,
      confidence,
      match_sources: sources,
      csv_match: csvMatch,
      goplus_flagged: goplusFlagged,
      goplus_details: goplusDetails,
      total_known_scams_in_db: knownScams.size,
    },
    error: null,
    cached: false,
    fetched_at: new Date().toISOString(),
  };
}
