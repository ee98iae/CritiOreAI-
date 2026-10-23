import { useEffect, useState } from "react";
import { api, Commodity, Region, ScoreResult, Target } from "./api";
import MapView, { Basemap } from "./MapView";

// Pilot commodities: where the real deposit data is. The API still accepts Ni and Co.
const COMMODITIES: Commodity[] = ["Cu", "W", "Au", "Mo"];
const NAMES: Record<Commodity, string> = {
  Cu: "Copper",
  W: "Tungsten",
  Au: "Gold",
  Mo: "Molybdenum",
  Ni: "Nickel",
  Co: "Cobalt",
};

export default function App() {
  const [region, setRegion] = useState<Region | null>(null);
  const [commodity, setCommodity] = useState<Commodity>("Cu");
  const [basemap, setBasemap] = useState<Basemap>("satellite");
  const [showGrid, setShowGrid] = useState(true);
  const [showOccurrences, setShowOccurrences] = useState(true);
  const [showMiners, setShowMiners] = useState(false);
  const [miners, setMiners] = useState<GeoJSON.FeatureCollection | null>(null);
  const [fitMongolia, setFitMongolia] = useState(0);
  const [occurrences, setOccurrences] = useState<GeoJSON.FeatureCollection | null>(null);
  const [grid, setGrid] = useState<GeoJSON.FeatureCollection | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [modelVersion, setModelVersion] = useState("");
  const [picked, setPicked] = useState<ScoreResult | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.regions().then((rs) => setRegion(rs[0] ?? null)).catch((e) => setError(String(e)));
    api.occurrences().then(setOccurrences).catch((e) => setError(String(e)));
    api.listedMiners().then(setMiners).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    setPicked(null);
    Promise.all([api.grid(commodity), api.targets(commodity)])
      .then(([g, t]) => {
        setGrid(g);
        setTargets(t.targets);
        setModelVersion(t.model_version);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  }, [commodity]);

  const onMapClick = (lat: number, lon: number) =>
    api.score(lat, lon, commodity).then(setPicked).catch((e) => setError(String(e)));

  const synthetic = occurrences?.features.some((f) => f.properties?.synthetic);

  return (
    <div className="layout">
      <aside className="panel">
        <header>
          <h1>CritiOre AI</h1>
          <p className="muted">{region?.name ?? "Loading region…"}</p>
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
              checked={showMiners}
              onChange={(e) => {
                setShowMiners(e.target.checked);
                if (e.target.checked) setFitMongolia((n) => n + 1);
              }}
            />{" "}
            Listed miners ({miners?.features.length ?? "…"} sites)
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

        <section className="legend">
          <span><i className="dot deposit" /> Deposit</span>
          <span><i className="dot occurrence" /> Occurrence</span>
          <span><i className="dot showing" /> Showing</span>
          <span><i className="ring" /> Ranked target</span>
          {showMiners && (
            <>
              <span><i className="dot miner producing" /> Listed: producing</span>
              <span><i className="dot miner development" /> Listed: development</span>
              <span><i className="dot miner other" /> Listed: other</span>
            </>
          )}
        </section>
        {showMiners && (
          <p className="muted small">
            Mines and projects run by publicly traded companies, checked Oct 2026. Click a marker for owners,
            tickers and sources.{" "}
            <button className="link" onClick={() => setFitMongolia((n) => n + 1)}>Show all of Mongolia</button>
          </p>
        )}

        {picked && (
          <section className="card">
            <h2>Clicked point</h2>
            <ScoreLine s={picked} />
            <EvidenceList s={picked} />
          </section>
        )}

        <section>
          <h2>Top {NAMES[commodity].toLowerCase()} targets</h2>
          <p className="muted small">Click the map anywhere to score that spot.</p>
          <ol className="targets">
            {targets.map((t) => (
              <li key={t.rank}>
                <button onClick={() => { setFocus({ lat: t.lat, lon: t.lon }); setPicked({ ...t, model_version: modelVersion }); }}>
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
        miners={miners}
        showMiners={showMiners}
        fitMongolia={fitMongolia}
        focus={focus}
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
