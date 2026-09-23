"use client";

import { useEffect, useRef, useState } from "react";
import type { FilterSpecification, Map as MlMap, MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import Dropdown from "@/components/ui/Dropdown";
import SliderSelect from "@/components/ui/SliderSelect";
import {
  ColorOnIcon,
  DitherOffIcon,
  DitherOnIcon,
  MediumStationsIcon,
  NormalStationsIcon,
  NormalTracksIcon,
  SettingsIcon,
  ThinStationsIcon,
  ThinTracksIcon,
} from "@/utils/icons/icons";

const DOT_SIZES = ["small", "medium", "large"] as const;
type DotSize = (typeof DOT_SIZES)[number];

/** Large is the previous circle size. Medium and small step down from it. */
const DOT_PAINT: Record<
  DotSize,
  { matched: number; missed: number; matchedStroke: number; missedStroke: number }
> = {
  small: { matched: 2, missed: 1.8, matchedStroke: 0.6, missedStroke: 1 },
  medium: { matched: 3.5, missed: 3.15, matchedStroke: 0.8, missedStroke: 1.3 },
  large: { matched: 5, missed: 4.5, matchedStroke: 1, missedStroke: 1.6 },
};

const DOT_SIZE_OPTIONS = [
  { value: "small" as const, label: "Small" },
  { value: "medium" as const, label: "Medium" },
  { value: "large" as const, label: "Large" },
];

/** Must match the close animation in globals.css. */
const SETTINGS_EXIT_MS = 140;

const COLOR_KEY = {
  speed: "color_speed",
  flow: "color_flow",
  travel: "color_travel",
} as const;
type Metric = keyof typeof COLOR_KEY;

type Properties = Record<string, string | number | boolean | null>;
type Bounds = { min_lon: number; min_lat: number; max_lon: number; max_lat: number };
type Manifest = {
  inputs: {
    osm_bounds: Bounds;
  };
};

/** Must match pipelines/tiles.py. */
const TILE_MIN_ZOOM = 5;
const TILE_MAX_ZOOM = 14;
const MOTORWAY_HIGHWAYS = ["motorway", "motorway_link", "trunk", "trunk_link"];
const PRIMARY_HIGHWAYS = [...MOTORWAY_HIGHWAYS, "primary", "primary_link"];

function roadFilter(mode: string): FilterSpecification | null {
  if (mode === "all") return null;
  const values = mode === "motorway" ? MOTORWAY_HIGHWAYS : PRIMARY_HIGHWAYS;
  return ["in", ["get", "highway"], ["literal", values]];
}

function viewBounds(bounds: Bounds): [[number, number], [number, number]] {
  return [
    [bounds.min_lon, bounds.min_lat],
    [bounds.max_lon, bounds.max_lat],
  ];
}

function escapeHtml(value: unknown) {
  return String(value ?? "—")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function popupHtml(properties: Properties) {
  const rows: Array<[string, unknown]> = [
    ["Site", properties.site_id],
    ["Name", properties.name],
    ["Road ref", properties.road_ref],
    ["OSM way", properties.osm_way_id],
    ["Highway", properties.highway],
    ["Confidence", properties.confidence],
    ["Distance m", properties.match_distance_m],
    ["Speed km/h", properties.metric_speed_kmh],
    ["Implied km/h", properties.metric_speed_implied_kmh],
    ["Flow veh/h", properties.metric_flow_vehh],
    ["Travel time s", properties.metric_travel_time_s],
    ["Time", properties.metric_time],
    ["Reason", properties.reason],
    ["Notes", properties.notes],
  ];
  return rows
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([label, value]) => `<div><span style="color:#9aa3b2">${escapeHtml(label)}</span> ${escapeHtml(value)}</div>`)
    .join("");
}

export default function MatchingCompare() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [painted, setPainted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<Metric>("speed");
  const [highway, setHighway] = useState("all");
  const [showDots, setShowDots] = useState(false);
  const [dotSize, setDotSize] = useState<DotSize>("small");
  const [ready, setReady] = useState(false);
  const mapNode = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const response = await fetch("/api/ndw-osm/comparison_manifest");
      if (!response.ok) {
        throw new Error("Manifest is missing. Run python3 pipelines/phase1.py match");
      }
      const body = (await response.json()) as Manifest;
      if (!cancelled) setManifest(body);
    })().catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!manifest || !mapNode.current) return;
    let cancelled = false;
    let frame = 0;
    const node = mapNode.current;
    const bounds = viewBounds(manifest.inputs.osm_bounds);
    (async () => {
      try {
      const maplibregl = await import("maplibre-gl");
      if (cancelled) return;
      maplibregl.setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");
      const tiles = [`${window.location.origin}/api/ndw-tiles/{z}/{x}/{y}`];
      const map = new maplibregl.Map({
        container: node,
        style: {
          version: 8,
          sources: {
            ndw: { type: "vector", tiles, minzoom: TILE_MIN_ZOOM, maxzoom: TILE_MAX_ZOOM },
          },
          layers: [
            { id: "background", type: "background", paint: { "background-color": "#101216" } },
            {
              id: "roads",
              type: "line",
              source: "ndw",
              "source-layer": "roads",
              paint: { "line-color": "#454d5c", "line-width": 1.15 },
            },
            {
              id: "matches",
              type: "line",
              source: "ndw",
              "source-layer": "matches",
              paint: { "line-color": ["get", "color_speed"], "line-width": 3 },
            },
            {
              id: "missed-sites",
              type: "circle",
              source: "ndw",
              "source-layer": "missed",
              layout: { visibility: "none" },
              paint: {
                "circle-radius": DOT_PAINT.small.missed,
                "circle-color": "transparent",
                "circle-stroke-color": "#f87171",
                "circle-stroke-width": DOT_PAINT.small.missedStroke,
              },
            },
            {
              id: "matched-sites",
              type: "circle",
              source: "ndw",
              "source-layer": "sites",
              layout: { visibility: "none" },
              paint: {
                "circle-radius": DOT_PAINT.small.matched,
                "circle-color": "#f8fafc",
                "circle-stroke-color": "#0f172a",
                "circle-stroke-width": DOT_PAINT.small.matchedStroke,
              },
            },
          ],
        },
        maxZoom: TILE_MAX_ZOOM,
        attributionControl: false,
        fadeDuration: 0,
        maxTileCacheSize: 2000,
        canvasContextAttributes: { preserveDrawingBuffer: true },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      const fit = (tries = 0) => {
        map.resize();
        const canvas = map.getCanvas();
        if (canvas.clientWidth >= 2 && canvas.clientHeight >= 2) {
          map.fitBounds(bounds, { padding: 48, duration: 0 });
          map.setMinZoom(map.getZoom());
          return;
        }
        if (tries < 30) frame = requestAnimationFrame(() => fit(tries + 1));
      };
      const onLoad = () => {
        if (cancelled) return;
        const open = (event: MapMouseEvent) => {
          const pad = 8;
          const found = map.queryRenderedFeatures(
            [
              [event.point.x - pad, event.point.y - pad],
              [event.point.x + pad, event.point.y + pad],
            ],
            { layers: ["matched-sites", "missed-sites", "matches"] },
          );
          const feature = found[0];
          if (!feature) return;
          const properties = (feature.properties ?? {}) as Properties;
          new maplibregl.Popup({ className: "ndw-popup", maxWidth: "320px" })
            .setLngLat(event.lngLat)
            .setHTML(popupHtml(properties))
            .addTo(map);
        };
        map.on("click", open);
        map.on("mouseenter", "matched-sites", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "matched-sites", () => {
          map.getCanvas().style.cursor = "";
        });
        map.on("mouseenter", "missed-sites", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "missed-sites", () => {
          map.getCanvas().style.cursor = "";
        });
        map.once("idle", () => {
          if (!cancelled) setPainted(true);
        });
        fit();
        setReady(true);
      };
      if (map.isStyleLoaded()) onLoad();
      else map.on("load", onLoad);
      mapRef.current = map;
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      }
    })();
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      mapRef.current?.remove();
      mapRef.current = null;
      setReady(false);
      setPainted(false);
    };
  }, [manifest]);

  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current;
    if (!map || !map.getLayer("roads")) return;
    const roads = roadFilter(highway);
    map.setFilter("roads", roads);
    map.setFilter("matches", roads);
    map.setFilter("matched-sites", roads);
    map.setPaintProperty("matches", "line-color", ["get", COLOR_KEY[metric]]);
    const dots = showDots ? "visible" : "none";
    map.setLayoutProperty("matched-sites", "visibility", dots);
    map.setLayoutProperty("missed-sites", "visibility", dots);
    const paint = DOT_PAINT[dotSize];
    map.setPaintProperty("matched-sites", "circle-radius", paint.matched);
    map.setPaintProperty("matched-sites", "circle-stroke-width", paint.matchedStroke);
    map.setPaintProperty("missed-sites", "circle-radius", paint.missed);
    map.setPaintProperty("missed-sites", "circle-stroke-width", paint.missedStroke);
  }, [ready, metric, highway, showDots, dotSize]);

  if (error) {
    return (
      <main className="p-8 text-sm">
        <h1 className="text-xl font-semibold">NDW–OSM matching</h1>
        <p className="mt-3 text-red-700">{error}</p>
      </main>
    );
  }

  return (
    <main className="flex h-dvh flex-col bg-neutral-950 text-neutral-100">
      <SettingsPanel
        metric={metric}
        highway={highway}
        showDots={showDots}
        dotSize={dotSize}
        onMetric={setMetric}
        onHighway={setHighway}
        onShowDots={setShowDots}
        onDotSize={setDotSize}
      />
      <div className="relative min-h-0 flex-1">
        {/* MapLibre sets .maplibregl-map { position: relative }, which drops Tailwind's absolute and collapses this pane to 0 height. */}
        <div ref={mapNode} className="absolute inset-0" style={{ position: "absolute", inset: 0 }} />
        {!painted && <p className="absolute bottom-3 left-3 text-sm text-neutral-400">Loading roads…</p>}
      </div>
    </main>
  );
}

const COLOUR_OPTIONS = [
  { value: "speed" as const, label: "Speed" },
  { value: "flow" as const, label: "Flow" },
  { value: "travel" as const, label: "Travel time" },
];
const ROAD_OPTIONS = [
  { value: "all", label: "All loaded" },
  { value: "motorway", label: "Motorway and trunk" },
  { value: "primary", label: "Through primary" },
];

function SettingsPanel({
  metric,
  highway,
  showDots,
  dotSize,
  onMetric,
  onHighway,
  onShowDots,
  onDotSize,
}: {
  metric: Metric;
  highway: string;
  showDots: boolean;
  dotSize: DotSize;
  onMetric: (metric: Metric) => void;
  onHighway: (highway: string) => void;
  onShowDots: (show: boolean) => void;
  onDotSize: (size: DotSize) => void;
}) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsMounted, setSettingsMounted] = useState(false);

  useEffect(() => {
    if (settingsOpen) {
      setSettingsMounted(true);
      return;
    }
    const timer = window.setTimeout(() => setSettingsMounted(false), SETTINGS_EXIT_MS);
    return () => window.clearTimeout(timer);
  }, [settingsOpen]);

  const RoadsIcon = highway === "all" ? NormalTracksIcon : ThinTracksIcon;
  const DotSizeIcon =
    dotSize === "small" ? ThinStationsIcon : dotSize === "medium" ? MediumStationsIcon : NormalStationsIcon;

  return (
    <div className="app-controls" data-settings-open={settingsOpen ? "true" : "false"}>
      <div className="app-controls-header">
        <div className="app-controls-title">NDW–OSM</div>
        <div className="app-controls-header-actions">
          <button
            type="button"
            className="app-controls-header-button"
            aria-label={settingsOpen ? "Hide settings" : "Show settings"}
            aria-expanded={settingsOpen}
            aria-pressed={settingsOpen}
            onClick={() => setSettingsOpen(!settingsOpen)}
          >
            <SettingsIcon />
          </button>
        </div>
      </div>

      {settingsMounted && (
        <div className="app-controls-settings-panel" data-open={settingsOpen ? "true" : "false"}>
          <div className="app-controls-divider" />
          <div className="app-controls-settings">
            <div className="app-controls-group">
              <div className="app-controls-section-title">Map</div>

              <div className="app-controls-field">
                <span className="app-controls-button" aria-hidden="true">
                  <ColorOnIcon />
                </span>
                <span className="app-controls-row-label">Colour</span>
                <Dropdown
                  className="app-controls-choice"
                  value={metric}
                  options={COLOUR_OPTIONS}
                  onChange={onMetric}
                  ariaLabel="Colour"
                  align="end"
                />
              </div>

              <div className="app-controls-field">
                <span className="app-controls-button" aria-hidden="true">
                  <RoadsIcon />
                </span>
                <span className="app-controls-row-label">Roads</span>
                <Dropdown
                  className="app-controls-choice"
                  value={highway}
                  options={ROAD_OPTIONS}
                  onChange={onHighway}
                  ariaLabel="Roads"
                  align="end"
                />
              </div>

              <button
                type="button"
                className="app-controls-row"
                onClick={() => onShowDots(!showDots)}
                title={showDots ? "Hide dots" : "Show dots"}
                aria-label={showDots ? "Dots shown. Hide dots" : "Dots hidden. Show dots"}
                aria-pressed={showDots}
              >
                <span className="app-controls-button" aria-hidden="true">
                  {showDots ? <DitherOnIcon /> : <DitherOffIcon />}
                </span>
                <span className="app-controls-row-label">Dots</span>
              </button>

              <div className="app-controls-field">
                <span className="app-controls-button" aria-hidden="true">
                  <DotSizeIcon />
                </span>
                <span className="app-controls-row-label">Dot size</span>
                <SliderSelect
                  value={dotSize}
                  options={DOT_SIZE_OPTIONS}
                  onChange={onDotSize}
                  ariaLabel="Dot size"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
