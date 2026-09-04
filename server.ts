import dotenv from "dotenv";
dotenv.config();

import express, { Request, Response } from "express";
import path from "path";
import cors from "cors";
import crypto from "crypto";
import { settings } from "./src/config.js";
import { createJob, getJob } from "./src/orchestrator/jobStore.js";
import { runInvestigation } from "./src/orchestrator/loop.js";
import { InvestigationStatus, TraceStep } from "./src/types.js";

const app = express();
const PORT = settings.port;

app.use(cors());
app.use(express.json());

// ── Static assets ────────────────────────────────────────────────────────────
const frontendPath = path.resolve(process.cwd(), "frontend");
app.use("/static", express.static(frontendPath));

app.get("/demo_addresses.txt", (req: Request, res: Response) => {
  res.sendFile(path.join(frontendPath, "demo_addresses.txt"));
});

// ── Health endpoint ──────────────────────────────────────────────────────────
app.get("/api/health", (req: Request, res: Response) => {
  res.json({ status: "ok", service: "ContractGuard" });
});

app.get("/health", (req: Request, res: Response) => {
  res.json({ status: "ok", service: "ContractGuard" });
});

// ── Start Investigation ──────────────────────────────────────────────────────
app.post("/investigate", (req: Request, res: Response) => {
  const { address, chain = "sepolia" } = req.body || {};

  if (!address || typeof address !== "string") {
    res.status(422).json({ error: "Address is required." });
    return;
  }

  const cleanAddr = address.trim();
  const ethAddressRegex = /^0x[0-9a-fA-F]{40}$/;
  if (!ethAddressRegex.test(cleanAddr)) {
    res.status(422).json({
      error: `Invalid Ethereum address '${cleanAddr}'. Must start with 0x and be 42 characters long.`,
    });
    return;
  }

  const jobId = crypto.randomUUID();
  const state = createJob(jobId, cleanAddr, chain);

  // Kick off asynchronous orchestrator investigation in background
  runInvestigation(state).catch((err) => {
    console.error(`Error in runInvestigation background task:`, err);
  });

  res.status(202).json({
    job_id: jobId,
    stream_url: `/stream/${jobId}`,
    report_url: `/report/${jobId}`,
    status: InvestigationStatus.PENDING,
  });
});

// ── SSE Stream ───────────────────────────────────────────────────────────────
app.get("/stream/:jobId", (req: Request, res: Response) => {
  const { jobId } = req.params;
  const state = getJob(jobId);

  if (!state) {
    res.status(404).json({ error: `Investigation job '${jobId}' not found.` });
    return;
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders?.();

  res.write(": ContractGuard SSE stream started\n\n");

  const unsubscribe = state.subscribe((step: TraceStep | null) => {
    if (step === null) {
      // Completed signal
      res.write(`data: ${JSON.stringify({ step_type: "complete", job_id: jobId })}\n\n`);
      res.end();
    } else {
      res.write(`data: ${JSON.stringify(step)}\n\n`);
    }
  });

  req.on("close", () => {
    unsubscribe();
  });
});

// ── Get Final Report ─────────────────────────────────────────────────────────
app.get("/report/:jobId", (req: Request, res: Response) => {
  const { jobId } = req.params;
  const state = getJob(jobId);

  if (!state) {
    res.status(404).json({ error: `Investigation job '${jobId}' not found.` });
    return;
  }

  if (state.status === InvestigationStatus.COMPLETE && state.finalReport) {
    res.json(state.finalReport);
    return;
  }

  if (state.status === InvestigationStatus.FAILED) {
    res.status(500).json({
      status: "failed",
      job_id: jobId,
      message: "Investigation failed",
      trace: state.trace,
    });
    return;
  }

  res.status(202).json({
    status: "running",
    job_id: jobId,
    message: "Investigation in progress",
  });
});

// ── Serve Frontend SPA ───────────────────────────────────────────────────────
app.use(express.static(frontendPath));

app.get("*", (req: Request, res: Response) => {
  res.sendFile(path.join(frontendPath, "index.html"));
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`ContractGuard server running on port ${PORT}`);
});
