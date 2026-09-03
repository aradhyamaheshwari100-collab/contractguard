import dotenv from "dotenv";
dotenv.config();

export const settings = {
  etherscanApiKey: process.env.ETHERSCAN_API_KEY || "",
  geminiApiKey: process.env.GEMINI_API_KEY || "",
  web3ProviderUrl: process.env.WEB3_PROVIDER_URL || "https://rpc.sepolia.org",
  goplusApiKey: process.env.GOPLUS_API_KEY || "",
  cacheTtlSeconds: parseInt(process.env.CACHE_TTL_SECONDS || "3600", 10),
  maxInvestigationDepth: parseInt(process.env.MAX_INVESTIGATION_DEPTH || "4", 10),
  escalationThresholdHistory: parseInt(process.env.ESCALATION_THRESHOLD_HISTORY || "70", 10),
  escalationThresholdCrossref: parseInt(process.env.ESCALATION_THRESHOLD_CROSSREF || "80", 10),
  port: parseInt(process.env.PORT || "3000", 10),
  host: process.env.HOST || "0.0.0.0",
  environment: process.env.ENVIRONMENT || "development",
  geminiModel: process.env.GEMINI_MODEL || "gemini-2.5-flash",
};
