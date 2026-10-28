# PostGIS Toolbox

A QGIS plugin for everyday work with PostGIS databases: managing databases and
schemas, loading vector and raster data, writing SQL, and running a handful of
PostGIS operations from the Processing toolbox.

## What it does

**Toolbar**

* **Manage databases** – pick a saved PostgreSQL connection, browse its
  databases, schemas and tables, create, rename or drop databases and schemas,
  check the PostGIS version and choose the database the other tools work on.
* **Import vector data** – load layers from the project or vector files
  (Shapefile, GeoPackage and other OGR formats) into a chosen schema, with
  options for spatial index, lower-case column names, single-part geometries
  and overwriting.
* **Import raster data** – load GeoTIFF rasters as PostGIS raster tables,
  tiled on the fly with optional overviews.
* **Query editor** – the QGIS DB Manager SQL window limited to PostGIS, with
  schema-qualified table names in the query builder, PostGIS function help and
  one-click "create table / create view" from the current query.
* **Table registry** – every table, view and raster in the active database in
  one list, with type, geometry type and SRID. Pick one to see its columns,
  primary key, indexes and raster overviews, add it to the project with a
  double click, rename it or drop it. Raster overviews are renamed and dropped
  together with their raster.
* The active database is shown on the toolbar; the icon next to it disconnects
  from it.

**Processing algorithms** (group *PostGIS Toolbox*)

* Vector: aggregate, buffer, clip, difference, intersection, merge, repair
  geometry, nearest neighbour, generate points, generate polygon from points.
* Raster: clip, merge tiles, reproject, resample, summary, tiles.

All algorithms run inside the database and can load the result back into the
project.

## Requirements

* QGIS 3.22 or newer (developed and tested on QGIS 3.44 LTR).
* A PostgreSQL server with the PostGIS extension (and `postgis_raster` for the
  raster tools).

The query editor builds on the DB Manager plugin that ships with QGIS, so no
extra Python packages are needed.

## Installation

Copy the `postgis_toolbox` folder into your QGIS plugin directory
(`Settings → User Profiles → Open Active Profile Folder`, then
`python/plugins`) or install it as a ZIP from *Plugins → Manage and Install
Plugins*. Then enable *PostGIS Toolbox* in the plugin manager.

## Languages

English and Polish. The Polish translation follows the QGIS interface
language.

## License

GNU General Public License v3, see [LICENSE](LICENSE).
