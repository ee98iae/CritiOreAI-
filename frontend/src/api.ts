export type Commodity = "Cu" | "W" | "Au" | "Mo" | "Ni" | "Co";

export interface Region {
  id: string;
  name: string;
  bbox: [number, number, number, number]; // south, west, north, east
  commodities: Commodity[];
}

export interface Evidence {
  id: string;
  name: string;
  type: string;
  commodities: string[];
  distance_km: number;
  contribution: number;
}

export interface ScoreResult {
  model_version: string;
  lat: number;
  lon: number;
  score: number;
  confidence: "low" | "medium" | "high";
  evidence: Evidence[];
}

export interface Target extends Omit<ScoreResult, "model_version"> {
  rank: number;
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  regions: () => get<Region[]>("/api/regions"),
  occurrences: (commodity?: Commodity) =>
    get<GeoJSON.FeatureCollection>(`/api/occurrences${commodity ? `?commodity=${commodity}` : ""}`),
  grid: (commodity: Commodity) => get<GeoJSON.FeatureCollection>(`/api/prospectivity/grid?commodity=${commodity}`),
  targets: (commodity: Commodity, limit = 10) =>
    get<{ model_version: string; targets: Target[] }>(`/api/targets?commodity=${commodity}&limit=${limit}`),
  score: (lat: number, lon: number, commodity: Commodity) =>
    get<ScoreResult>("/api/prospectivity/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon, commodity }),
    }),
};
