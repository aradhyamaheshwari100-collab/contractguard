import { GoogleGenAI } from "@google/genai";
import { AgentFindings, Finding, FindingSeverity } from "../types.js";
import { settings } from "../config.js";

const JSON_EXTRACT_RE = /(\{[\s\S]*\}|\[[\s\S]*\])/;

let genAIClient: GoogleGenAI | null = null;

function getGenAI(): GoogleGenAI | null {
  if (!genAIClient && settings.geminiApiKey) {
    try {
      genAIClient = new GoogleGenAI({ apiKey: settings.geminiApiKey });
    } catch (e) {
      console.warn("Failed to initialize GoogleGenAI client:", e);
    }
  }
  return genAIClient;
}

export abstract class BaseAgent {
  abstract agentName: string;
  modelName: string = settings.geminiModel;

  protected async callLLM(prompt: string): Promise<Record<string, any>> {
    const ai = getGenAI();
    if (!ai) {
      throw new Error("GEMINI_API_KEY is not configured");
    }

    let lastError: any = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const strictPrompt =
          attempt > 0
            ? `${prompt}\n\nCRITICAL: Return ONLY valid, parseable JSON. No markdown fences, no explanatory text.`
            : prompt;

        const response = await ai.models.generateContent({
          model: this.modelName,
          contents: strictPrompt,
          config: {
            temperature: 0.1,
            maxOutputTokens: 2048,
          },
        });

        let raw = response.text || "";
        raw = raw.replace(/^```(?:json)?\s*/m, "").replace(/\s*```\s*$/m, "").trim();

        try {
          return JSON.parse(raw);
        } catch {
          const match = JSON_EXTRACT_RE.exec(raw);
          if (match) {
            return JSON.parse(match[1]);
          }
          throw new Error(`JSON parsing failed on output: ${raw.slice(0, 100)}...`);
        }
      } catch (err: any) {
        lastError = err;
        await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
      }
    }
    throw lastError || new Error("LLM call failed after 3 attempts");
  }

  protected parseFindings(raw: Record<string, any>): AgentFindings {
    const findingsRaw = Array.isArray(raw.findings) ? raw.findings : [];
    const findings: Finding[] = [];

    const severityMap: Record<string, FindingSeverity> = {
      critical: FindingSeverity.CRITICAL,
      high: FindingSeverity.HIGH,
      medium: FindingSeverity.MEDIUM,
      low: FindingSeverity.LOW,
      info: FindingSeverity.INFO,
      warning: FindingSeverity.MEDIUM,
      warn: FindingSeverity.MEDIUM,
    };

    for (let i = 0; i < findingsRaw.length; i++) {
      const item = findingsRaw[i];
      if (!item) continue;
      const sevStr = String(item.severity || "medium").toLowerCase();
      const severity = severityMap[sevStr] || FindingSeverity.MEDIUM;

      findings.push({
        id: `FINDING-${Math.random().toString(36).substring(2, 8).toUpperCase()}`,
        severity,
        category: String(item.category || "general"),
        title: String(item.title || "Untitled finding"),
        description: String(item.description || ""),
        evidence: item.evidence ? String(item.evidence) : null,
        raw_snippet: item.raw_snippet ? String(item.raw_snippet) : null,
        agent: this.agentName,
      });
    }

    let score = typeof raw.suspicion_score === "number" ? raw.suspicion_score : 50;
    score = Math.max(0, Math.min(100, Math.round(score)));

    return {
      agent: this.agentName,
      suspicion_score: score,
      confidence: raw.confidence === "high" || raw.confidence === "low" ? raw.confidence : "medium",
      findings,
      summary: String(raw.summary || ""),
      insufficient_data: Boolean(raw.insufficient_data),
    };
  }
}
