import { settings } from "../config.js";
import { RiskVerdict } from "../types.js";

export const THRESHOLD_ESCALATE_HISTORY = settings.escalationThresholdHistory; // default 70
export const THRESHOLD_ESCALATE_CROSSREF = settings.escalationThresholdCrossref; // default 80
export const MAX_DEPTH = settings.maxInvestigationDepth; // default 4

export const VERDICT_LOW_MAX = 30;
export const VERDICT_MEDIUM_MAX = 69;

export function scoreToVerdict(score: number): { verdict: RiskVerdict; label: string } {
  if (score <= VERDICT_LOW_MAX) {
    return { verdict: RiskVerdict.LOW, label: "Low Risk" };
  } else if (score <= VERDICT_MEDIUM_MAX) {
    return { verdict: RiskVerdict.MEDIUM, label: "Medium Risk — Proceed with Caution" };
  } else {
    return { verdict: RiskVerdict.HIGH, label: "High Fraud Risk — Do Not Interact" };
  }
}
