import { useEffect, useRef } from "react";
import maplibregl, { GeoJSONSource, Map as MlMap, StyleSpecification } from "maplibre-gl";
import type { Region, Target } from "./api";

export type Basemap = "streets" | "satellite";

const BASEMAPS: Record<Basemap, { tiles: string[]; attribution: string }> = {
  streets: {
    tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    attribution: "© OpenStreetMap contributors",
  },
  satellite: {
    tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
  },
};

// Mongolia's extent, for the listed-miners layer which covers the whole country.
const MONGOLIA_BOUNDS: [[number, number], [number, number]] = [[87.7, 41.5], [120.0, 52.2]];
const MINER_COLORS = ["match", ["get", "status"], "producing", "#7b2cbf", "development", "#c77dff", "#e0d3ee"];

const OCC_COLORS = ["match", ["get", "type"], "deposit", "#d7263d", "occurrence", "#f49d37", "#3f88c5"];

function style(basemap: Basemap): StyleSpecification {
  return {
    version: 8,
    sources: { base: { type: "raster", tileSize: 256, ...BASEMAPS[basemap] } },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#dcd6c8" } },
      { id: "base", type: "raster", source: "base" },
    ],
  };
}

interface Props {
  region: Region | null;
  basemap: Basemap;
  occurrences: GeoJSON.FeatureCollection | null;
  grid: GeoJSON.FeatureCollection | null;
  targets: Target[];
  showGrid: boolean;
  showOccurrences: boolean;
  miners: GeoJSON.FeatureCollection | null;
  showMiners: boolean;
  fitMongolia: number;
  focus: { lat: number; lon: number } | null;
  onMapClick: (lat: number, lon: number) => void;
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function addDataLayers(map: MlMap) {
  map.addSource("grid", { type: "geojson", data: EMPTY });
  map.addSource("occurrences", { type: "geojson", data: EMPTY });
  map.addSource("miners", { type: "geojson", data: EMPTY });
  map.addLayer({
    id: "grid",
    type: "fill",
    source: "grid",
    paint: {
      "fill-color": ["interpolate", ["linear"], ["get", "score"], 0, "#fff5b1", 0.4, "#fd8d3c", 0.8, "#800026"],
      "fill-opacity": ["interpolate", ["linear"], ["get", "score"], 0, 0.1, 1, 0.65],
    },
  });
  map.addLayer({
    id: "occurrences",
    type: "circle",
    source: "occurrences",
    paint: {
      "circle-radius": ["match", ["get", "type"], "deposit", 7, "occurrence", 5, 4],
      "circle-color": OCC_COLORS as never,
      "circle-stroke-color": "#fff",
      "circle-stroke-width": 1.2,
    },
  });
  map.addLayer({
    id: "miners",
    type: "circle",
    source: "miners",
    layout: { visibility: "none" },
    paint: {
      "circle-radius": 8,
      "circle-color": MINER_COLORS as never,
      "circle-stroke-color": "#1b1035",
      "circle-stroke-width": 2.5,
    },
  });
}

// Built with textContent and checked https links: fields come from curated but external data.
function minerPopup(p: Record<string, unknown>): HTMLElement {
  const parse = <T,>(v: unknown): T => (typeof v === "string" ? JSON.parse(v) : v) as T;
  const companies = parse<{ name: string; tickers: string[]; stake: string }[]>(p.companies);
  const commodities = parse<string[]>(p.commodities);
  const sources = parse<string[]>(p.sources);
  const el = document.createElement("div");
  el.className = "miner-popup";
  el.appendChild(document.createElement("strong")).textContent = String(p.site);
  el.appendChild(document.createElement("div")).textContent =
    `${p.status} · ${commodities.join(", ")} · ${p.province}`;
  const list = el.appendChild(document.createElement("ul"));
  for (const c of companies) {
    list.appendChild(document.createElement("li")).textContent = `${c.name} (${c.tickers.join(", ")}), ${c.stake}`;
  }
  el.appendChild(document.createElement("div")).textContent = String(p.ownership);
  if (p.note) el.appendChild(document.createElement("small")).textContent = String(p.note);
  const src = el.appendChild(document.createElement("div"));
  src.className = "small";
  src.append(`As of ${p.as_of}${p.precision === "approximate" ? " · location approximate" : ""} · `);
  sources.filter((u) => u.startsWith("https://")).forEach((u, i) => {
    const a = src.appendChild(document.createElement("a"));
    a.href = u;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = `source ${i + 1}`;
    src.append(" ");
  });
  return el;
}

export default function MapView(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  // Set once our sources exist. isStyleLoaded() is unreliable here: it stays
  // false while basemap tiles are still loading or failing.
  const ready = useRef(false);
  const latest = useRef(props);
  latest.current = props;

  // Create the map once.
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: style(props.basemap),
      center: [91.7, 49.6],
      zoom: 7,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    map.on("load", () => {
      addDataLayers(map);
      ready.current = true;
      syncData(map, latest.current);
    });
    map.on("click", (e) => latest.current.onMapClick(e.lngLat.lat, e.lngLat.lng));
    map.on("click", "occurrences", (e) => {
      const p = e.features?.[0]?.properties;
      if (!p) return;
      const commodities = JSON.parse(p.commodities as string).join(", ");
      // Built with textContent: occurrence fields come from imported data.
      const el = document.createElement("div");
      const title = el.appendChild(document.createElement("strong"));
      title.textContent = p.name;
      el.appendChild(document.createElement("div")).textContent = `${p.type} · ${commodities}`;
      const src = el.appendChild(document.createElement("small"));
      src.textContent = `${p.source}${p.synthetic ? " · synthetic" : ""}`;
      new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(el).addTo(map);
    });
    map.on("click", "miners", (e) => {
      const p = e.features?.[0]?.properties;
      if (p) new maplibregl.Popup({ maxWidth: "320px" }).setLngLat(e.lngLat).setDOMContent(minerPopup(p)).addTo(map);
    });
    map.on("mouseenter", "miners", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "miners", () => (map.getCanvas().style.cursor = ""));
    map.on("mouseenter", "occurrences", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "occurrences", () => (map.getCanvas().style.cursor = ""));
    mapRef.current = map;
    return () => {
      ready.current = false;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (map && ready.current) syncData(map, props);
  }, [props.occurrences, props.grid, props.showGrid, props.showOccurrences, props.miners, props.showMiners]);

  useEffect(() => {
    if (props.fitMongolia && mapRef.current) mapRef.current.fitBounds(MONGOLIA_BOUNDS, { padding: 20 });
  }, [props.fitMongolia]);

  // Ranked targets are HTML markers, so their labels need no remote font glyphs.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const markers = props.targets.map((t) => {
      const el = document.createElement("div");
      el.className = "target-marker";
      el.textContent = String(t.rank);
      el.title = `Target #${t.rank}: ${(t.score * 100).toFixed(0)}/100`;
      return new maplibregl.Marker({ element: el }).setLngLat([t.lon, t.lat]).addTo(map);
    });
    return () => markers.forEach((m) => m.remove());
  }, [props.targets]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("base");
    if (src && "setTiles" in src) (src as maplibregl.RasterTileSource).setTiles(BASEMAPS[props.basemap].tiles);
  }, [props.basemap]);

  useEffect(() => {
    const { region } = props;
    if (region && mapRef.current) {
      const [s, w, n, e] = region.bbox;
      mapRef.current.fitBounds([[w, s], [e, n]], { padding: 30, duration: 0 });
    }
  }, [props.region]);

  useEffect(() => {
    if (props.focus && mapRef.current) {
      mapRef.current.flyTo({ center: [props.focus.lon, props.focus.lat], zoom: Math.max(mapRef.current.getZoom(), 9) });
    }
  }, [props.focus]);

  return <div ref={container} className="map" />;
}

function syncData(map: MlMap, p: Props) {
  (map.getSource("grid") as GeoJSONSource | undefined)?.setData(p.grid ?? EMPTY);
  (map.getSource("occurrences") as GeoJSONSource | undefined)?.setData(p.occurrences ?? EMPTY);
  if (map.getLayer("grid")) map.setLayoutProperty("grid", "visibility", p.showGrid ? "visible" : "none");
  if (map.getLayer("occurrences"))
    map.setLayoutProperty("occurrences", "visibility", p.showOccurrences ? "visible" : "none");
  (map.getSource("miners") as GeoJSONSource | undefined)?.setData(p.miners ?? EMPTY);
  if (map.getLayer("miners")) map.setLayoutProperty("miners", "visibility", p.showMiners ? "visible" : "none");
}
