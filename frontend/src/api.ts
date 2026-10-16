export type Commodity = "Cu" | "Ni" | "Co" | "Au" | "Mo";

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

export interface User {
  email: string;
  name: string;
  role: "team" | "client";
  regions: string[];
}

export interface LayerInfo {
  id: string;
  title: string;
  group: "Imagery" | "Terrain" | "Alteration" | string;
  description: string;
  source: string;
  units: string;
  kind: "continuous" | "rgb";
  colormap: string | null;
  rescale: [number, number] | null;
  acquired: string;
  bounds: [number, number, number, number]; // west, south, east, north
  legend: string[];
}

export interface LayerManifest {
  region: string;
  built: boolean;
  built_at?: string;
  cell_size_m?: [number, number];
  sentinel2_scenes?: string[];
  layers: LayerInfo[];
}

const TOKEN_KEY = "critiore.token";

// Storage can be unavailable (private windows, blocked site data); the session then lasts until reload.
let memoryToken: string | null = null;
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}
function setToken(token: string | null) {
  memoryToken = token;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* keep the in-memory copy */
  }
}

export class Unauthorized extends Error {}
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    setToken(null);
    onUnauthorized();
    throw new Unauthorized("Signed out");
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<User> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (res.status === 401) throw new Error("Wrong email or password.");
  if (!res.ok) throw new Error(`Sign-in failed (${res.status}).`);
  const body = (await res.json()) as { token: string; user: User };
  setToken(body.token);
  return body.user;
}

export function logout() {
  setToken(null);
}

export const tileUrl = (region: string, layer: string) =>
  `${window.location.origin}/api/layers/${region}/${layer}/tiles/{z}/{x}/{y}.png`;

export const api = {
  me: () => get<User>("/api/auth/me"),
  layers: (region: string) => get<LayerManifest>(`/api/layers?region=${region}`),
  layerValues: (region: string, lat: number, lon: number) =>
    get<{ values: Record<string, number | null> }>(`/api/layers/${region}/values?lat=${lat}&lon=${lon}`),
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
