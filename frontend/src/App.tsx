import { useEffect, useState } from "react";
import {
  api,
  Commodity,
  getToken,
  LayerInfo,
  LayerManifest,
  logout,
  Region,
  ScoreResult,
  setUnauthorizedHandler,
  Target,
  Unauthorized,
  User,
} from "./api";
import Login from "./Login";
import MapView, { Basemap, RasterLayer } from "./MapView";

const COMMODITIES: Commodity[] = ["Cu", "Ni", "Co", "Au", "Mo"];
const NAMES: Record<Commodity, string> = { Cu: "Copper", Ni: "Nickel", Co: "Cobalt", Au: "Gold", Mo: "Molybdenum" };

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(() => getToken() !== null);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    if (getToken()) {
      api.me().then(setUser).catch(() => setUser(null)).finally(() => setChecking(false));
    }
  }, []);

  if (checking) return <main className="login muted">Loading…</main>;
  if (!user) return <Login onLogin={setUser} />;
  return (
    <Workspace
      user={user}
      onLogout={() => {
        logout();
        setUser(null);
      }}
    />
  );
}

const GROUP_ORDER = ["Alteration", "Imagery", "Terrain"];

interface LayerState {
  visible: boolean;
  opacity: number;
}

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [region, setRegion] = useState<Region | null>(null);
  const [commodity, setCommodity] = useState<Commodity>("Cu");
  const [basemap, setBasemap] = useState<Basemap>("satellite");
  const [showGrid, setShowGrid] = useState(true);
  const [showOccurrences, setShowOccurrences] = useState(true);
  const [occurrences, setOccurrences] = useState<GeoJSON.FeatureCollection | null>(null);
  const [grid, setGrid] = useState<GeoJSON.FeatureCollection | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [modelVersion, setModelVersion] = useState("");
  const [picked, setPicked] = useState<ScoreResult | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manifest, setManifest] = useState<LayerManifest | null>(null);
  const [layerState, setLayerState] = useState<Record<string, LayerState>>({});
  const [pickedValues, setPickedValues] = useState<Record<string, number | null> | null>(null);

  const report = (e: unknown) => {
    if (!(e instanceof Unauthorized)) setError(String(e));
  };

  useEffect(() => {
    api.regions().then((rs) => setRegion(rs[0] ?? null)).catch(report);
    api.occurrences().then(setOccurrences).catch(report);
  }, []);

  useEffect(() => {
    if (!region) return;
    api
      .layers(region.id)
      .then((m) => {
        setManifest(m);
        // Start with the imagery and one alteration layer on, so the map shows real data at once.
        const initial: Record<string, LayerState> = {};
        for (const l of m.layers) initial[l.id] = { visible: l.id === "true_colour", opacity: l.kind === "rgb" ? 1 : 0.75 };
        setLayerState(initial);
      })
      .catch(report);
  }, [region]);

  useEffect(() => {
    setPicked(null);
    Promise.all([api.grid(commodity), api.targets(commodity)])
      .then(([g, t]) => {
        setGrid(g);
        setTargets(t.targets);
        setModelVersion(t.model_version);
        setError(null);
      })
      .catch(report);
  }, [commodity]);

  const loadValues = (lat: number, lon: number) => {
    setPickedValues(null);
    if (region && manifest?.built) api.layerValues(region.id, lat, lon).then((v) => setPickedValues(v.values)).catch(report);
  };

  const onMapClick = (lat: number, lon: number) => {
    api.score(lat, lon, commodity).then(setPicked).catch(report);
    loadValues(lat, lon);
  };

  const setLayer = (id: string, patch: Partial<LayerState>) =>
    setLayerState((s) => ({ ...s, [id]: { ...s[id], ...patch } }));

  const rasterLayers: RasterLayer[] =
    region && manifest
      ? manifest.layers.map((info) => ({ region: region.id, info, ...(layerState[info.id] ?? { visible: false, opacity: 1 }) }))
      : [];

  const synthetic = occurrences?.features.some((f) => f.properties?.synthetic);

  return (
    <div className="layout">
      <aside className="panel">
        <header>
          <h1>CritiOre AI</h1>
          <p className="muted">{region?.name ?? "Loading region…"}</p>
          <div className="userbar muted">
            <span>
              {user.name} · {user.role === "team" ? "Team" : "Client (read-only)"}
            </span>
            <button className="linkish" onClick={onLogout}>
              Sign out
            </button>
          </div>
        </header>

        {error && <p className="error">Can't reach the API: {error}</p>}
        {synthetic && (
          <p className="notice">Showing synthetic demo occurrences. Load real data with the MRDS importer.</p>
        )}

        <section>
          <label htmlFor="commodity">Target commodity</label>
          <select id="commodity" value={commodity} onChange={(e) => setCommodity(e.target.value as Commodity)}>
            {COMMODITIES.map((c) => (
              <option key={c} value={c}>
                {NAMES[c]} ({c})
              </option>
            ))}
          </select>
        </section>

        <section className="toggles">
          <label>
            <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} /> Prospectivity
          </label>
          <label>
            <input type="checkbox" checked={showOccurrences} onChange={(e) => setShowOccurrences(e.target.checked)} />{" "}
            Known occurrences
          </label>
          <label>
            <input
              type="checkbox"
              checked={basemap === "satellite"}
              onChange={(e) => setBasemap(e.target.checked ? "satellite" : "streets")}
            />{" "}
            Satellite basemap
          </label>
        </section>

        <section>
          <h2>Data layers</h2>
          {manifest && !manifest.built && (
            <p className="muted small">No layers built for this region yet. Run the layer pipeline on the server.</p>
          )}
          {manifest?.built && (
            <LayerControls manifest={manifest} state={layerState} onChange={setLayer} />
          )}
        </section>

        <section className="legend">
          <span><i className="dot deposit" /> Deposit</span>
          <span><i className="dot occurrence" /> Occurrence</span>
          <span><i className="dot showing" /> Showing</span>
          <span><i className="ring" /> Ranked target</span>
        </section>

        {picked && (
          <section className="card">
            <h2>Clicked point</h2>
            <ScoreLine s={picked} />
            <EvidenceList s={picked} />
            {pickedValues && manifest && <LayerValues manifest={manifest} values={pickedValues} />}
          </section>
        )}

        <section>
          <h2>Top {NAMES[commodity].toLowerCase()} targets</h2>
          <p className="muted small">Click the map anywhere to score that spot.</p>
          <ol className="targets">
            {targets.map((t) => (
              <li key={t.rank}>
                <button onClick={() => { setFocus({ lat: t.lat, lon: t.lon }); setPicked({ ...t, model_version: modelVersion }); loadValues(t.lat, t.lon); }}>
                  <span className="rank">#{t.rank}</span>
                  <ScoreLine s={t} />
                </button>
              </li>
            ))}
          </ol>
        </section>

        <footer className="muted small">Model: {modelVersion || "…"} (placeholder, not a trained model)</footer>
      </aside>

      <MapView
        region={region}
        basemap={basemap}
        occurrences={occurrences}
        grid={grid}
        targets={targets}
        showGrid={showGrid}
        showOccurrences={showOccurrences}
        focus={focus}
        rasterLayers={rasterLayers}
        onMapClick={onMapClick}
      />
    </div>
  );
}

function ScoreLine({ s }: { s: Pick<ScoreResult, "score" | "confidence" | "lat" | "lon"> }) {
  return (
    <span className="scoreline">
      <b>{(s.score * 100).toFixed(0)}</b>
      <span className="muted">/100 · {s.confidence} confidence</span>
      <span className="muted small coords">
        {s.lat.toFixed(3)}°N {s.lon.toFixed(3)}°E
      </span>
    </span>
  );
}

function EvidenceList({ s }: { s: ScoreResult }) {
  if (!s.evidence.length) return <p className="muted small">No known occurrences nearby.</p>;
  return (
    <ul className="evidence">
      {s.evidence.map((e) => (
        <li key={e.id}>
          {e.name} <span className="muted">({e.type}, {e.commodities.join("/")}) {e.distance_km} km</span>
        </li>
      ))}
    </ul>
  );
}

function fmt(v: number): string {
  const a = Math.abs(v);
  return a >= 100 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : v.toFixed(2);
}

function LayerControls({
  manifest,
  state,
  onChange,
}: {
  manifest: LayerManifest;
  state: Record<string, LayerState>;
  onChange: (id: string, patch: Partial<LayerState>) => void;
}) {
  const groups = [...new Set(manifest.layers.map((l) => l.group))].sort(
    (a, b) => (GROUP_ORDER.indexOf(a) + 99) % 99 - (GROUP_ORDER.indexOf(b) + 99) % 99,
  );
  return (
    <div className="layer-group">
      {groups.map((g) => (
        <div key={g} className="layer-group">
          <h3>{g}</h3>
          {manifest.layers
            .filter((l) => l.group === g)
            .map((l) => {
              const st = state[l.id] ?? { visible: false, opacity: 1 };
              return (
                <div key={l.id} className="layer">
                  <div className="layer-row">
                    <label title={l.description}>
                      <input type="checkbox" checked={st.visible} onChange={(e) => onChange(l.id, { visible: e.target.checked })} />{" "}
                      {l.title}
                    </label>
                    {st.visible && (
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={st.opacity}
                        aria-label={`${l.title} opacity`}
                        onChange={(e) => onChange(l.id, { opacity: Number(e.target.value) })}
                      />
                    )}
                  </div>
                  {st.visible && <LayerLegend layer={l} />}
                </div>
              );
            })}
        </div>
      ))}
      <p className="muted small">
        Sentinel-2 {manifest.layers.find((l) => l.acquired)?.acquired ?? ""}
        {manifest.cell_size_m ? ` · ${manifest.cell_size_m[0]} × ${manifest.cell_size_m[1]} m cells` : ""}
      </p>
    </div>
  );
}

function LayerLegend({ layer }: { layer: LayerInfo }) {
  return (
    <div>
      <p className="muted small" style={{ margin: "0 0 4px" }}>
        {layer.description}
      </p>
      {layer.legend.length > 0 && layer.rescale && (
        <>
          <div className="ramp" style={{ background: `linear-gradient(to right, ${layer.legend.join(", ")})` }} />
          <div className="ramp-labels">
            <span>{fmt(layer.rescale[0])}</span>
            <span>{layer.units}</span>
            <span>{fmt(layer.rescale[1])}</span>
          </div>
        </>
      )}
    </div>
  );
}

function LayerValues({ manifest, values }: { manifest: LayerManifest; values: Record<string, number | null> }) {
  const rows = manifest.layers.filter((l) => l.id in values);
  if (!rows.length) return null;
  return (
    <ul className="values">
      {rows.map((l) => (
        <li key={l.id} style={{ display: "contents" }}>
          <span className="muted">{l.title}</span>
          <span>
            {values[l.id] === null ? "–" : fmt(values[l.id] as number)} {values[l.id] === null ? "" : l.units}
          </span>
        </li>
      ))}
    </ul>
  );
}
