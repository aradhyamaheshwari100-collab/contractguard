import fs from "fs";
import path from "path";
import { ToolResult } from "../types.js";
import { settings } from "../config.js";

export interface ScamRecord {
  address: string;
  label: string;
  source: string;
  date_added: string;
  is_scam: boolean;
}

let cachedScamDatabase: {
  scamMap: Map<string, ScamRecord>;
  scamCount: number;
} | null = null;

function resolveCsvPath(): string | null {
  const configured = settings.knownScamsFilePath || "data/known_scams.csv";
  const candidatePaths = [
    path.isAbsolute(configured) ? configured : path.resolve(process.cwd(), configured),
    path.resolve(process.cwd(), "data", "known_scams.csv"),
    path.resolve(process.cwd(), "../data", "known_scams.csv"),
    "/data/known_scams.csv",
  ];

  for (const p of candidatePaths) {
    if (fs.existsSync(p)) {
      return p;
    }
  }
  return null;
}

function loadScamDatabase(): { scamMap: Map<string, ScamRecord>; scamCount: number } {
  if (cachedScamDatabase) {
    return cachedScamDatabase;
  }

  const scamMap = new Map<string, ScamRecord>();
  let scamCount = 0;

  try {
    const csvPath = resolveCsvPath();
    if (csvPath) {
      const content = fs.readFileSync(csvPath, "utf-8");
      const lines = content.split("\n");
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        const parts = line.split(",");
        const addr = parts[0]?.trim().toLowerCase();
        if (addr && addr.startsWith("0x") && addr.length === 42) {
          const label = parts[1]?.trim() || "Reported scam entity";
          const source = parts[2]?.trim() || "Threat Intelligence CSV";
          const dateAdded = parts[3]?.trim() || "";
          
          // Check if this entry is a benign/false-positive test address
          const lowerLabel = label.toLowerCase();
          const isNotScam = lowerLabel.includes("not scam") || lowerLabel.includes("false positive");
          const isScam = !isNotScam;

          const record: ScamRecord = {
            address: addr,
            label,
            source,
            date_added: dateAdded,
            is_scam: isScam,
          };

          scamMap.set(addr, record);
          if (isScam) {
            scamCount++;
          }
        }
      }
    } else {
      console.warn("Could not locate known_scams.csv static threat list.");
    }
  } catch (err) {
    console.warn("Failed to read known_scams.csv:", err);
  }

  cachedScamDatabase = { scamMap, scamCount };
  return cachedScamDatabase;
}

export async function searchKnownScamLists(address: string): Promise<ToolResult> {
  const addrLower = address.toLowerCase();
  const { scamMap, scamCount } = loadScamDatabase();
  const record = scamMap.get(addrLower);

  const matched = Boolean(record && record.is_scam);
  const sources: string[] = [];

  if (matched && record) {
    sources.push(record.source || "CryptoScamDB static list");
  }

  const confidence: "none" | "low" | "medium" | "high" = matched ? "high" : "none";

  return {
    tool: "search_known_scam_lists",
    success: true,
    insufficient_data: false,
    data: {
      address,
      matched,
      confidence,
      match_sources: sources,
      csv_match: matched,
      record: record
        ? {
            label: record.label,
            source: record.source,
            date_added: record.date_added,
            is_scam: record.is_scam,
          }
        : null,
      known_benign: Boolean(record && !record.is_scam),
      total_known_scams_in_db: scamCount,
    },
    error: null,
    cached: false,
    fetched_at: new Date().toISOString(),
  };
}
