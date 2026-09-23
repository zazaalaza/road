import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FILES: Record<string, string> = {
  osm_roads: "processed/osm_roads.geojson",
  ndw_sites: "processed/ndw_sites.geojson",
  ndw_segments: "processed/ndw_segments.geojson",
  ndw_latest_metrics: "processed/ndw_latest_metrics.json",
  comparison_manifest: "matches/comparison_manifest.json",
  method_point_snap: "matches/method_point_snap.geojson",
  method_point_snap_unmatched: "matches/method_point_snap_unmatched.json",
};

export async function GET(
  _request: Request,
  context: { params: Promise<{ dataset: string }> },
) {
  const { dataset } = await context.params;
  const relative = FILES[dataset];
  if (!relative) {
    return NextResponse.json({ error: "unknown dataset" }, { status: 404 });
  }
  try {
    const body = await readFile(path.join(process.cwd(), "data", relative));
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
