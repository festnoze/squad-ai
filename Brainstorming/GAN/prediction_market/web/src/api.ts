import type { SignalStudy, AgentSummary, CampaignAnalysis, CampaignDetail, CampaignJob, CampaignRequest, CampaignSummary, DatasetSummary, Job, MarketDetail, MarketSummary, RunDetail, RunMarketReplay, RunRequest, RunSummary } from "./types";

async function json<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch {
    throw new Error("Le serveur local est injoignable. VÃ©rifiez que pmx est dÃ©marrÃ© sur le port 8175, puis rÃ©essayez.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : `Erreur du serveur (${response.status})`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
const segment = encodeURIComponent;
const queryString = (filters: Record<string, string>) =>
  new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== "")).toString();
export const api = {
  signalStudies: () => json<{ studies: SignalStudy[] }>("/signal-studies"),
  signalStudy: (id: string) => json<SignalStudy>(`/signal-studies/${segment(id)}`),
  startSignalStudy: (dataset: string) => json<SignalStudy>("/signal-studies", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dataset }) }),
  datasets: () => json<{ datasets: DatasetSummary[] }>("/datasets"),
  agents: () => json<{ agents: AgentSummary[] }>("/agents"),
  markets: (dataset: string, filters: Record<string, string>) => json<{ items: MarketSummary[]; total: number; page: number; page_size: number }>(`/datasets/${segment(dataset)}/markets?${queryString(filters)}`),
  market: (dataset: string, market: string) => json<MarketDetail>(`/datasets/${segment(dataset)}/markets/${segment(market)}`),
  startRun: (request: RunRequest) => json<Job>("/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) }),
  job: (id: string) => json<Job>(`/jobs/${segment(id)}`),
  runs: () => json<{ runs: RunSummary[] }>("/runs"),
  run: (id: string) => json<RunDetail>(`/runs/${segment(id)}`),
  replay: (id: string, market: string) => json<RunMarketReplay>(`/runs/${segment(id)}/markets/${segment(market)}`),
  campaigns: () => json<{ campaigns: CampaignSummary[] }>("/campaigns"),
  startCampaign: (request: CampaignRequest) => json<CampaignJob>("/campaigns", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) }),
  campaign: (id: string) => json<CampaignDetail>(`/campaigns/${segment(id)}`),
  analysis: (id: string) => json<CampaignAnalysis>(`/campaigns/${segment(id)}/analysis`),
  requestAnalysis: (id: string) => json<CampaignAnalysis>(`/campaigns/${segment(id)}/analysis`, { method: "POST" }),
  analysisSettings: (enabled: boolean) => json<{ enabled: boolean }>("/analysis/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) }),
  cancelJob: (id: string) => json<Job>(`/jobs/${segment(id)}/cancel`, { method: "POST" }),
};
