import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PUBLIC_MANIFEST = path.join(process.cwd(), "public", "ndw", "comparison_manifest.json");

const FILES: Record<string, string> = {
  osm_roads: "processed/osm_roads.geojson",
  ndw_sites: "processed/ndw_sites.geojson",
  ndw_segments: "processed/ndw_segments.geojson",
  ndw_latest_metrics: "processed/ndw_latest_metrics.json",
  method_point_snap: "matches/method_point_snap.geojson",
  method_point_snap_unmatched: "matches/method_point_snap_unmatched.json",
};

export async function GET(
  _request: Request,
  context: { params: Promise<{ dataset: string }> },
) {
  const { dataset } = await context.params;
  const relative = FILES[dataset];
  const file = dataset === "comparison_manifest" ? PUBLIC_MANIFEST : relative && path.join(process.cwd(), "data", relative);
  if (!file) {
    return NextResponse.json({ error: "unknown dataset" }, { status: 404 });
  }
  try {
    const body = await readFile(file);
    return new NextResponse(body, {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: "file not built yet",
        hint: "python3 pipelines/phase1.py all",
      },
      { status: 404 },
    );
  }
}
