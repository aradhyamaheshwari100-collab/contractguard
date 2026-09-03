import { InvestigationState } from "./state.js";

const jobs = new Map<string, InvestigationState>();

export function createJob(jobId: string, address: string, chain: string): InvestigationState {
  const state = new InvestigationState(jobId, address, chain);
  jobs.set(jobId, state);
  return state;
}

export function getJob(jobId: string): InvestigationState | undefined {
  return jobs.get(jobId);
}

export function listJobs(): string[] {
  return Array.from(jobs.keys());
}
