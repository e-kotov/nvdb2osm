# nvdbswe2osm

Converts NVDB in Sweden to OSM file with tagging.

### Usage

1. Order the relevant municipality data from [Lastkajen](https://lastkajen.trafikverket.se/) at Trafikverket.
   * You need to register first (it is free).
   * Choose the _Homogeniserad_ format.
   * Choose the municipality.
   * Check for all attributes.
   * Download the GeoDB folder when it is ready (you get a mail).

2. **GeoJSON (no external dependencies):**

   Convert the FileGDB to GeoJSON in QGIS or with `ogr2ogr`, reprojecting to
   WGS84 (EPSG:4326). Then run:

   <code>python3 nvdbswe2osm.py \<municipality.geojson\> [-o output.osm] [-segment]</code>
 
    * The script auto-detects WGS84 coordinates — no external packages needed.
    * If coordinates are not in WGS84 (e.g. EPSG:3006), the script will attempt to reproject using `pyproj`. If `pyproj` is not installed, it exits with a suggested `ogr2ogr` command to reproject the file.

 3. **FileGDB (the original format that you get from the Lastkajen portal with custom export), GeoPackage, or Shapefile** (requires `fiona` and `pyproj`):
 
    <code>python3 nvdbswe2osm.py \<municipality.gdb\> [-o output.osm] [-segment]</code>
 
    * Coordinates are automatically transformed to WGS84 from the source CRS.
 
    Options for both modes:
    * **`-o`, `--output`**: Specify output filename. Supports `.osm` (XML) and `.pbf` (Protocolbuffer) extensions (default: `output.osm`).
    * **`--format`**: Force output format (`osm` or `pbf`). Defaults to `osm` unless `.pbf` extension is detected.
      * *Note: PBF output requires `osmium` (`pip install osmium`).*
    * The <code>-segment</code> option includes all NVDB attributes and does not combine segments into longer ways.
    * Use <code>--layer NAME</code> to specify a layer for multi-layer files.
    * Use <code>--source-crs EPSG:XXXX</code> to override CRS detection.

### Notes

* Current implementation is provided as is, it is still experimental, use at your own risk.
* Highways are combined into longer ways. There are three different methods to choose from in the program.
* Highways are split at sharp turns.
* Way polygons are simplified with a factor of 0.20 meters.
* Most municipalities are generated in a few seconds. The largest municipalities in Sweden run in a couple of minutes.

### Supported tags

Highway classification, `ref`, `name`, `maxspeed`, `oneway`, `junction=roundabout`, `motor_vehicle=no`, `overtaking=no`, `surface`, `width`, `lanes`, `psv`, `bridge`, `tunnel`, `layer`, `maxheight`, `maxlength`, `maxweight`, `maxaxleload`, `maxwidth:physical`, `hazmat`, `low_emission_zone`, `lit`, `bicycle=designated`, `motorroad`, `priority_road`, `traffic_calming`, `barrier`, railway crossings, rest areas, and ferry routes.

### Future work

* **~~HGV restrictions~~** — ✅ Implemented. `Framkomlighet för vissa fordonskombinationer` (class 4) now maps to `hgv=no` on forest roads.
* **~~Specific vehicle type restrictions~~** — ✅ Implemented. NVDB vehicle type codes (buss, lastbil, tung lastbil, etc.) now map to appropriate OSM tags (`vehicle=no`, `hgv=no`, `access=no`, etc.) with weight-based conditional restrictions where applicable.
* **~~Directional gross weight limits~~** — ✅ Implemented. `Begränsad bruttovikt` produces `maxweight` / `maxweight:forward` / `maxweight:backward`. Bridge-based maxweight from `Bärighet` serves as fallback.
* **~~Hazmat restrictions~~** — ✅ Implemented. `Inskränkningar för transport av farligt gods` maps to `hazmat=no` (directional). `Rekommenderad väg för farligt gods` maps to `hazmat=designated`.
* **~~Environmental zones~~** — ✅ Implemented. `Miljözon` maps to `low_emission_zone=yes`.
* **~~Barrier passable width~~** — ✅ Implemented. `Väghinder/Passerbar bredd` adds `maxwidth:physical` to barrier nodes.
* **Conditional restrictions** — ❌ NOT IMPLEMENTABLE. Time-based restrictions (`Tidsintervall`) from NVDB are not included in the Lastkajen FileGDB export. According to official documentation, this data has only ~2% completeness nationwide. The `FörbudTrafik/Beskrivning` fields in the export contain only route descriptions and vehicle exemptions, not time intervals.
* **Detailed lane information** — `Körfältsinformation` (`Korfa_524`) contains per-lane data that could produce `lanes:forward`, `lanes:backward`, and `turn:lanes` tags. The per-lane fields are not available in the Lastkajen FileGDB export.
* **Traffic volume** — ÅDT fields (12 attributes) are loaded but not mapped to any OSM tags. No established OSM convention exists for traffic volume data.

### NVDB attributes not converted

Some NVDB attributes are intentionally not converted:

* **No OSM schema** — Traffic volume (ÅDT), turning possibility class (`Vändmöjlighet`), strategic HGV network designation, seasonal bearing class, axle type codes.
* **Infrastructure/maintenance** — Noise barriers, road barriers/guardrails, road surface details (beyond paved/unpaved), anti-glare screens, winter maintenance class, construction/reconstruction years, drainage, weather stations, calibration roads.
* **Network metadata** — NVDB link roles, TEN-T network IDs, network topology identifiers.
* **Covered by other logic** — Europaväg boolean (E-road refs derived from road category + number), road type codes (highway classification uses functional road class), sub-road numbers and county affiliation.
* **Low value for routing** — Traffic calming position within segment, bus stop flags (better as separate nodes), parking pockets, detailed rest area amenities (restaurant, showers), railway crossing metadata beyond barrier type.
* **Requires complex parsing** — Weight restriction text descriptions (would need conditional tag parsing), per-lane turn codes (data not in export), climbing lanes.

### References

* [Trafikverket NVDB](https://www.nvdb.se/sv)
* [Trafikverket Lastkajen](https://lastkajen.trafikverket.se/)
