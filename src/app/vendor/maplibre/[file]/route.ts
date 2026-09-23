import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

export const runtime = "nodejs";

const FILES = new Set(["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]);

export async function GET(
  _request: Request,
  context: { params: Promise<{ file: string }> },
) {
  const { file } = await context.params;
  if (!FILES.has(file)) {
    return new NextResponse("not found", { status: 404 });
  }
  const body = await readFile(path.join(process.cwd(), "node_modules/maplibre-gl/dist", file));
  return new NextResponse(body, {
    headers: {
      "Content-Type": "text/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=86400",
    },
  });
}
