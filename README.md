# Roads

## What this is

This project matches two datasets — NDW traffic measurement sites and OSM roads in the Netherlands — and shows the traffic on a map. Each site is snapped to the nearest OSM way within 25 m, and a short stretch of that way is coloured by speed, flow, or travel time.

## Run

```
npm install
```

Installs the Next.js dependencies. The pipeline uses the Python standard library plus the `osmium` and `tippecanoe` command-line tools.

```
npm run phase1
```

Downloads NDW and the Geofabrik Netherlands OSM extract if they are missing, matches sites, and builds vector tiles. Same as `python3 pipelines/phase1.py all`.

```
npm run phase1:metrics
```

Refreshes the minute speed and travel-time files, rematches, and rebuilds tiles.

```
npm run phase1:match
```

Rematches from the processed files already on disk and rebuilds tiles.

```
npm run phase1:tiles
```

Rebuilds vector tiles from the GeoJSON on disk. Same as `python3 pipelines/tiles.py`.

```
npm run phase1:selftest
```

Runs a small in-memory check of name parsing and point snap. No downloads.

```
npm run dev
```

Starts the app.

http://localhost:3000/experiments/ndw-osm-matching

The matching map.

## Structure

`pipelines/phase1.py` fetches NDW and OSM, normalizes them, point-snap matches, and builds tiles. Radius, highlight length, and highway classes are in `pipelines/matching_config.json`.

`pipelines/ndw.py` reads the national NDW measurement file and the minute speed and travel-time publications, and keeps every site.

`pipelines/osm.py` filters the Netherlands PBF with osmium to the configured highway classes and writes road lines. There is no bounding-box clip.

`pipelines/matchers.py` snaps each site to the nearest OSM way within 25 m and writes a short highlight along that way, with colours for speed, flow, and travel time. The spatial index and the clip are in `pipelines/geo.py`.

`pipelines/tiles.py` turns those GeoJSON files into one vector-tile set with tippecanoe, so the browser requests tiles instead of retiling the full files.

`data/` is produced by the pipeline and gitignored.

`src/app/experiments/ndw-osm-matching/page.tsx` is the experiment page. `src/components/ndw-osm/MatchingCompare.tsx` is one MapLibre map: matches coloured by speed, flow, or travel time, with settings for road class, site dots, and dot size.

`src/app/api/ndw-tiles/[z]/[x]/[y]/route.ts` serves tiles from `data/tiles/ndw.mbtiles`. `src/app/api/ndw-osm/[dataset]/route.ts` serves the manifest and GeoJSON.
