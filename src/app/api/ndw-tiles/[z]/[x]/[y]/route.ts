import { statSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TILE_PATH = path.join(process.cwd(), "data/tiles/ndw.mbtiles");

type TileDb = {
  mtimeMs: number;
  db: DatabaseSync;
  select: {
    get: (...args: number[]) => { tile_data: Uint8Array } | undefined;
  };
};

let cached: TileDb | null = null;

function tileDb(): TileDb | null {
  let mtimeMs: number;
  try {
    mtimeMs = statSync(TILE_PATH).mtimeMs;
  } catch {
    return null;
  }
  if (cached && cached.mtimeMs === mtimeMs) return cached;
  cached?.db.close();
  const db = new DatabaseSync(TILE_PATH, { readOnly: true });
  cached = {
    mtimeMs,
    db,
    select: db.prepare(
      "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
    ) as TileDb["select"],
  };
  return cached;
}

function integer(value: string) {
  if (!/^\d+$/.test(value)) return null;
  const number = Number(value);
  return Number.isSafeInteger(number) ? number : null;
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ z: string; x: string; y: string }> },
) {
  const { z: zText, x: xText, y: yText } = await context.params;
  const z = integer(zText);
  const x = integer(xText);
  const y = integer(yText);
  if (z === null || x === null || y === null || z > 22) {
    return new NextResponse("bad tile", { status: 400 });
  }
  const db = tileDb();
  if (!db) {
    return NextResponse.json(
      { error: "tiles not built yet", hint: "python3 pipelines/tiles.py" },
      { status: 404 },
    );
  }
  const row = (1 << z) - 1 - y;
  const found = db.select.get(z, x, row);
  if (!found) {
    return new NextResponse(null, { status: 204 });
  }
  const bytes = found.tile_data;
  const gzip = bytes.byteLength >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
  return new NextResponse(Buffer.from(bytes), {
    headers: {
      "Content-Type": "application/vnd.mapbox-vector-tile",
      ...(gzip ? { "Content-Encoding": "gzip" } : {}),
      "Cache-Control": "public, max-age=86400",
    },
  });
}
