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

type DotSize = ["small", "medium", "large"][number];

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
  const sections: Array<[string, Array<[string, unknown]>]> = [
    [
      "Location",
      [
        ["Site", properties.site_id],
        ["Name", properties.name],
        ["Road ref", properties.road_ref],
        ["OSM way", properties.osm_way_id],
        ["Highway", properties.highway],
      ],
    ],
    [
      "Data",
      [
        ["Speed km/h", properties.metric_speed_kmh],
        ["Implied km/h", properties.metric_speed_implied_kmh],
        ["Flow veh/h", properties.metric_flow_vehh],
        ["Travel time s", properties.metric_travel_time_s],
      ],
    ],
    [
      "Meta",
      [
        ["Distance", properties.match_distance_m],
        ["Confidence", properties.confidence],
        ["Notes", properties.notes],
        ["Time", properties.metric_time],
        ["Reason", properties.reason],
      ],
    ],
  ];
  return sections
    .flatMap(([heading, rows]) => {
      const visible = rows.filter(([, value]) => value !== null && value !== undefined && value !== "");
      return visible.length === 0 ? [] : [[heading, visible] as const];
    })
    .map(([heading, rows], index) => {
      const gap = index === 0 ? "" : "margin-top:8px;";
      const title = `<div style="${gap}color:#6e7787;font-size:10px">${escapeHtml(heading)}</div>`;
      const body = rows
        .map(([label, value]) => `<div><span style="color:#9aa3b2">${escapeHtml(label)}</span> ${escapeHtml(value)}</div>`)
        .join("");
      return title + body;
    })
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
  const syncCursorRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const response = await fetch("/ndw/comparison_manifest.json");
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
      const tiles = [`${window.location.origin}/ndw-tiles/{z}/{x}/{y}.pbf`];
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
          const fittedZoom = map.getZoom();
          const frame = map.getBounds();
          map.setMinZoom(fittedZoom);
          map.setMaxBounds(frame);
          return;
        }
        if (tries < 30) frame = requestAnimationFrame(() => fit(tries + 1));
      };
      const onLoad = () => {
        if (cancelled) return;
        const interactiveLayers = ["matched-sites", "missed-sites", "matches"] as const;
        const featuresAt = (point: MapMouseEvent["point"]) => {
          const pad = 8;
          return map.queryRenderedFeatures(
            [
              [point.x - pad, point.y - pad],
              [point.x + pad, point.y + pad],
            ],
            { layers: [...interactiveLayers] },
          );
        };
        const open = (event: MapMouseEvent) => {
          const feature = featuresAt(event.point)[0];
          if (!feature) return;
          const properties = (feature.properties ?? {}) as Properties;
          new maplibregl.Popup({ className: "ndw-popup", maxWidth: "320px" })
            .setLngLat(event.lngLat)
            .setHTML(popupHtml(properties))
            .addTo(map);
        };
        let pointer: MapMouseEvent["point"] | null = null;
        const syncCursor = () => {
          map.getCanvas().style.cursor = pointer && featuresAt(pointer).length ? "pointer" : "";
        };
        syncCursorRef.current = syncCursor;
        map.on("click", open);
        map.on("mousemove", (event) => {
          pointer = event.point;
          syncCursor();
        });
        map.on("mouseout", () => {
          pointer = null;
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
      syncCursorRef.current = null;
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
    map.once("idle", () => {
      syncCursorRef.current?.();
    });
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
        <ColourLegend metric={metric} />
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

/** Same stops as pipelines/matchers.py. Missing values are #6b7280 in every metric. */
const MISSING_COLOR = "#6b7280";

type LegendStop = { value: number; color: string };

const COLOUR_STOPS: Record<Metric, { title: string; unit: string; stops: LegendStop[] }> = {
  speed: {
    title: "Speed",
    unit: "km/h",
    stops: [
      { value: 0, color: "#d73027" },
      { value: 40, color: "#fc8d59" },
      { value: 70, color: "#fee08b" },
      { value: 100, color: "#1a9850" },
    ],
  },
  flow: {
    title: "Flow",
    unit: "veh/h",
    stops: [
      { value: 0, color: "#e0f3f8" },
      { value: 800, color: "#67a9cf" },
      { value: 2500, color: "#2166ac" },
    ],
  },
  travel: {
    title: "Travel time",
    unit: "seconds",
    stops: [
      { value: 0, color: "#1a9850" },
      { value: 45, color: "#fee08b" },
      { value: 120, color: "#d73027" },
    ],
  },
};

function legendGradient(stops: LegendStop[]) {
  const max = stops[stops.length - 1]?.value ?? 1;
  return `linear-gradient(to right, ${stops
    .map((stop) => `${stop.color} ${max === 0 ? 0 : (stop.value / max) * 100}%`)
    .join(", ")})`;
}

function ColourLegend({ metric }: { metric: Metric }) {
  const legend = COLOUR_STOPS[metric];
  const max = legend.stops[legend.stops.length - 1]?.value ?? 1;
  return (
    <div className="ndw-legend">
      <div className="ndw-legend-title">
        <span>{legend.title}</span>
        <span className="ndw-legend-unit">{legend.unit}</span>
      </div>
      <div className="ndw-legend-bar" style={{ background: legendGradient(legend.stops) }} />
      <div className="ndw-legend-labels">
        {legend.stops.map((stop, index) => {
          const at = max === 0 ? 0 : (stop.value / max) * 100;
          const edge = index === 0 ? "start" : index === legend.stops.length - 1 ? "end" : "mid";
          return (
            <span key={stop.value} className="ndw-legend-label" data-edge={edge} style={{ left: `${at}%` }}>
              {stop.value}
            </span>
          );
        })}
      </div>
      <div className="ndw-legend-missing">
        <span className="ndw-legend-swatch" style={{ background: MISSING_COLOR }} />
        Missing
      </div>
    </div>
  );
}

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
  const [closing, setClosing] = useState(false);
  const settingsMounted = settingsOpen || closing;
  const closeTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    };
  }, []);

  const toggleSettings = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    if (settingsOpen) {
      setSettingsOpen(false);
      setClosing(true);
      closeTimer.current = window.setTimeout(() => {
        closeTimer.current = null;
        setClosing(false);
      }, SETTINGS_EXIT_MS);
      return;
    }
    setClosing(false);
    setSettingsOpen(true);
  };

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
            onClick={toggleSettings}
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
              <div className="app-controls-section-title">Roads</div>

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
            </div>

            <div className="app-controls-group">
              <div className="app-controls-section-title">Markers</div>

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
