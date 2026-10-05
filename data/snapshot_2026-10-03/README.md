# Frozen data snapshot — 3 October 2026

This folder holds the exact IMF PortWatch downloads behind every published figure of Zero Hormuz Monitor v0.3 / v0.3.1 (port data to 25 Sep 2026; Hormuz transits to 27 Sep 2026). Do not edit these files. A new download is a new cut, not a recovery of this one.

| File | Content | Rows | Coverage |
|---|---|---|---|
| `ports_daily_2026-10-03.csv` | Daily port calls and import/export tonnes by vessel type, 18 ports (UAE and Oman) | 50,850 | 2019-01-01 to 2026-09-25 |
| `hormuz_daily_2026-10-03.csv` | Daily transits through the Strait of Hormuz (chokepoint6) by vessel type | 2,827 | 2019-01-01 to 2026-09-27 |
| `ports_catalog_2026-10-03.csv` | PortWatch port database records for the 18 ports | 18 | — |

**Retrieved:** 2026-10-03, from the IMF PortWatch ArcGIS REST API.

## Queries

Each file is the result of one paginated query to
`https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/<service>/FeatureServer/0/query`
with the parameters `outFields=*`, `returnGeometry=false`, `f=json`, `orderByFields=ObjectId`, `resultRecordCount=2000` and `resultOffset` advanced by the number of records returned, until the service reports no more records. The code is `fetch()` and `load()` in `src/zero_hormuz_monitor.py`.

| File | Service | `where` clause |
|---|---|---|
| `ports_daily_2026-10-03.csv` | `Daily_Ports_Data` | `portid IN (<18 port ids>) AND year>=2019` |
| `hormuz_daily_2026-10-03.csv` | `Daily_Chokepoints_Data` | `portid='chokepoint6' AND year>=2019` |
| `ports_catalog_2026-10-03.csv` | `PortWatch_ports_database` | `portid IN (<18 port ids>)` |

The 18 port ids are: `port744` Jebel Ali, `port2025` Khalifa Port, `port5` Abu Dhabi, `port306` Dubai, `port72` Sharjah, `port13` Ajman, `port1340` Umm al Qaiwain, `port747` Mina Saqr, `port22` Al Hamriyah LPG Terminal, `port512` Jabal Az Zannah-Ruways, `port2236` Jebel Dhanna, `port2237` Das Island, `port2235` Zirku Island (UAE Gulf coast); `port362` Fujairah, `port561` Khor Fakkan (UAE east coast); `port988` Port of Sohar, `port746` Salalah, `port984` Duqm (Oman, comparison only).

## Integrity

SHA-256 hashes are in `SHA256SUMS`:

```bash
cd data/snapshot_2026-10-03 && sha256sum -c SHA256SUMS
```

On Windows: `Get-FileHash -Algorithm SHA256 <file>` and compare with `SHA256SUMS`.

## Reproduce the published cut (no download)

From the repository root:

```bash
python src/zero_hormuz_monitor.py --data-dir data/snapshot_2026-10-03 --out-dir outputs_repro --powerbi
cd outputs_repro && sha256sum -c ../outputs/SHA256SUMS
```

The seven CSV files in `outputs_repro/` must match `outputs/SHA256SUMS` byte for byte (checked on 2026-10-04). The Excel file is rebuilt with the same tables, but its file hash changes on every run because of internal timestamps.

`--refresh` is refused together with `--data-dir`, so this snapshot can never be overwritten. The weekly update is a separate procedure (see the main README).

## Source and terms

Source: International Monetary Fund, PortWatch (https://portwatch.imf.org). All PortWatch volumes are AIS-based estimates, not official statistics. IMF data may be reused and redistributed for non-commercial purposes with attribution to the IMF; commercial reuse requires IMF permission (https://www.imf.org/en/about/copyright-and-terms). The MIT license of this repository applies to the code only, not to these data.
