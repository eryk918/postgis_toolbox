# PostGIS Toolbox

A QGIS plugin for the everyday PostGIS stuff: databases and schemas, loading
vectors and rasters, keeping tables in shape, writing SQL and running a bunch
of PostGIS operations straight from the Processing toolbox. Everything runs
in the database, QGIS just drives.

## What's in the box

**Toolbar**

* **Manage databases** – pick a saved PostgreSQL connection (new ones go
  through the regular QGIS connection dialog), see what's on the server,
  add / rename / drop databases and schemas, check PostGIS, and choose the
  database the rest of the plugin works on. "Last used" gets you back to
  yesterday's database in one click, the filter box narrows the tree down.
  "Sessions" shows who's connected, what they run, for how long and who
  blocks whom, with buttons to cancel a query or kick a session.
* **Import vector data** – project layers or files (Shapefile, GeoPackage,
  anything OGR reads) into a schema of your choice, with spatial index,
  lower-case column names, single-part geometries and overwrite options.
* **Import raster data** – GeoTIFFs from the project or from disk, many at
  once. Tiled on the fly (presets or your own tile size), LZW-compressed,
  overviews if you want them. Imports run in the background with a progress
  bar on the message bar, and a few can run side by side. Loaded layers land
  in the "Imported vectors" / "Imported rasters" groups.
* **Table registry** – every table, view and raster of the active database in
  one list with type, geometry and SRID. Click one and you get its size, last
  vacuum, owner, privileges, comments, columns, keys, indexes, raster
  resolution and overviews. Double-click to add it to the project or drag it
  onto the map. From there you can export it (the QGIS save-as dialogs),
  rename, move, copy (also to another database), drop, vacuum, index, add a
  primary key, fix the SRID or geometry type, check geometries, rebuild
  overviews, add raster constraints, retile, edit comments, grab the CREATE
  statement, and manage styles saved in `layer_styles`. Privileges can be set
  per table or for a whole schema, default privileges for future tables
  included. "Health check" lists tables without a key or spatial index,
  bloated or never analysed tables, unused indexes and rasters without
  constraints, each with a Fix button. Long jobs run in the background with
  real progress where Postgres gives it (vacuum, index builds). Right-click
  for the same menu, Delete key drops the selected object.
* **Projects in database** – QGIS projects stored in the database, per
  schema, through the same project storage QGIS uses in *Project → Open
  from / Save to*. Open, save the current project, delete the old ones.
* **Query editor** – the QGIS DB Manager SQL window trimmed to PostGIS, with
  schema-qualified table names in the builder, PostGIS function help and
  "create table / view" from the current query.
* **SQL log** – everything the plugin ran, with timing and errors, ready to
  copy or save as .txt / .log when something goes wrong.
* The active database sits on the toolbar, the icon next to it disconnects.
  Import dialogs remember the last schema and options.

**Processing algorithms** (group *PostGIS Toolbox*)

* Vector: aggregate, buffer, centroids, clip, cluster (DBSCAN), difference,
  dissolve, intersection, merge, repair geometry, nearest neighbour,
  simplify, Voronoi polygons, generate points, generate polygon from points.
* Raster: clip, merge tiles, reproject, resample, summary, tiles, terrain
  analysis (slope, aspect, hillshade), raster to polygons, zonal statistics.

Results can be loaded back into the project right away.

## Requirements

* QGIS 3.34.9 or newer (developed and tested on QGIS 3.44 LTR).
* PostgreSQL with PostGIS, plus `postgis_raster` for the raster tools.

The query editor builds on the DB Manager plugin that ships with QGIS, so no
extra Python packages are needed.

## Installation

Copy the `postgis_toolbox` folder into your QGIS plugin directory
(`Settings → User Profiles → Open Active Profile Folder`, then
`python/plugins`) or install the ZIP from *Plugins → Manage and Install
Plugins*. Then enable *PostGIS Toolbox* in the plugin manager.

## Languages

English and Polish, following the QGIS interface language.

## License

GNU General Public License v3, see [LICENSE](LICENSE).
