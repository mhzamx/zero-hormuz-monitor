# Zero Hormuz Monitor

**How much UAE port activity survived the 2026 closure of the Strait of Hormuz, and could the east-coast ports make up the difference?**

An open, reproducible data pipeline (Python → SQLite → Excel) and a six-page Power BI dashboard built on IMF PortWatch vessel-tracking (AIS) estimates. It measures UAE port activity from 1 March to 25 September 2026 against what would normally have moved, and tests whether Fujairah and Khor Fakkan (outside the strait) compensated for the Gulf-coast ports.

![Dashboard – summary page](docs/images/p1_summary.png)

> Dashboard labels, table names and some code comments are in Spanish; this README is in English.
>
> Version 0.3 · data through 25 Sep 2026 (PortWatch, consulted 3 Oct 2026).

---

## Key findings (1 Mar – 25 Sep 2026)

| Indicator | Result | Range across 5 reference methods |
|---|---|---|
| UAE port activity preserved, all cargo (tonnes) | **27.7 %** of the normal level | 26.2 – 28.2 % |
| UAE container activity preserved | **16.1 %** | 14.5 – 16.2 % |
| Gulf-coast container loss offset by the east coast | **4.2 %** | 4.2 – 4.7 % |
| East coast, all cargo | **−23.7 Mt** (own loss, mainly Fujairah tankers) | no net compensation under any method |
| Residual gap, all cargo | **211.3 Mt** not moved through UAE ports | 205.9 – 227.0 Mt |

**Validation against official figures.** PortWatch tonnes track official TEU changes closely for Jebel Ali containers: Q2 2026 year on year **−90.9 %** (PortWatch) vs **−90.1 %** (DP World); H1 2026 **−58.9 %** vs **−59.5 %**. Results are validated on percentage changes, not on absolute levels.

### Why the east coast cannot replace Jebel Ali

![Dashboard – why the east coast does not compensate](docs/images/p6_why_not_replace.png)

1. **Size.** Official container capacity: Khor Fakkan 5.0 M TEU + Fujairah 0.72 M TEU = 5.72 M TEU, about **30 %** of Jebel Ali's 19.4 M TEU.
2. **Specialization.** Fujairah is an oil and bulk port. Share of its tonnes, Mar–Sep 2025: 85.0 % tankers, 14.8 % dry bulk, 0.1 % containers. In 2026 containers rose only to **5.3 %**.
3. **Saturation.** Khor Fakkan ran at roughly 97 % of its 3.5 M TEU/year capacity in July. Its 4-week container average peaked at 216.0 kt (week to 2 Aug) and then fell **22 %** to 168.0 kt, despite an expansion to 5 M TEU.
4. **Land connection.** A rail freight service to Fujairah only started on 27 Sep 2026; trucking capacity and anchorage waiting times were reported as constraints.

At its best 4-week run, the whole east coast moved about **7 %** of the container tonnes Jebel Ali handled in a normal week.

---

## Method

**Data.** Daily port-call and cargo-volume estimates for 18 port areas (13 on the UAE Gulf coast, Fujairah and Khor Fakkan on the east coast, and Sohar, Salalah and Duqm in Oman), plus daily Strait of Hormuz transits, downloaded from the IMF PortWatch open ArcGIS API.

**Segments.** Containers · General cargo + RoRo · Dry bulk · Tankers · Non-tankers · Total.

**Reference ("what would normally have moved").** Five baselines, so every headline number comes with a sensitivity range:

| Code | Baseline |
|---|---|
| M1 | Same weekday 52 weeks earlier (364-day lag) |
| M2 | M1 adjusted for pre-shock growth (sensitivity only) |
| **M3** | **Average of the same weekday 52 and 104 weeks earlier (main reference)** |
| M4 | Average level of the 8 weeks before the shock (28 Feb 2026) |
| M5 | M3 adjusted for pre-shock growth (sensitivity only) |

**Indicators.**

- *Activity preserved* = (Gulf-coast actual + east-coast actual) ÷ (Gulf-coast reference + east-coast reference).
- *Gap decomposition*: (a) Gulf-coast loss, (b) east-coast compensation or own loss, (c) Oman credited (kept at 0 until there is evidence of diverted UAE cargo), (d) residual gap.
- *Alerts*: weekly spikes above a 26-week rolling median + 3 median absolute deviations, and jumps in tonnes per port call. They flag weeks to investigate; they are not confirmed errors.

**Backtest without future information.** Each baseline was tested on three windows before the shock (Mar–Sep 2024, Mar–Sep 2025, Dec 2025–Feb 2026). Median weekly WAPE across groups and segments: M4 15.0 % · M3 16.2 % · M5 17.2 % · M1 20.3 % · M2 21.5 %. For Gulf-coast containers, the segment that drives the headline, M3 averages 9.1 %.

**Known limitations.**

- All PortWatch volumes are AIS-based **estimates**: vessels without a signal, port-area boundaries and transshipment adjustments can bias levels.
- PortWatch records fewer Hormuz transits than Lloyd's List (31 vs 73 in the week of 10–16 Aug 2026), so transits are used for trend only.
- Isolated spikes (e.g. Abu Dhabi in March and June 2026) may be vessels anchored inside the port area.
- The monitor measures cargo that moved, not unmet demand or the capacity that would have been needed.

---

## Dashboard (Power BI)

| Page | Content |
|---|---|
| 1 · Resumen (Summary) | Activity preserved, sensitivity range, residual gap, east-coast change, and a waterfall from the reference to observed activity |
| 2 · Semanal (Weekly) | Weekly activity preserved; Gulf coast and east coast, actual vs reference |
| 3 · Puertos (Ports) | Who lost and who absorbed: port matrix, monthly east coast and Oman tonnes, sustained weekly throughput |
| 4 · Ormuz (Hormuz) | Weekly transits through the strait vs reference, and monthly transits by vessel type |
| 5 · Método (Method) | Validation against official figures, backtest WAPE, definitions and data-quality alerts |
| 6 · ¿Por qué no reemplazan? (Why not replace?) | Size, specialization, saturation and land connection |

<details>
<summary>Screenshots of pages 2–5</summary>

![Weekly](docs/images/p2_weekly.png)
![Ports](docs/images/p3_ports.png)
![Hormuz](docs/images/p4_hormuz.png)
![Method](docs/images/p5_method.png)

</details>

The full report is also available as a PDF: [`docs/ZeroHormuz_Monitor_v0.3.pdf`](docs/ZeroHormuz_Monitor_v0.3.pdf).

**Model.** Star schema with 15 tables (date, port and segment dimensions; daily port and Hormuz facts; summary tables) and 36 DAX measures. The semantic model is stored as TMDL in [`powerbi/semantic-model/`](powerbi/semantic-model/) so measures and relationships can be read and diffed as text.

---

## Repository structure

```
zero-hormuz-monitor/
├── src/zero_hormuz_monitor.py        # pipeline: PortWatch API → SQLite → indicators → Power BI package
├── requirements.txt
├── outputs/                          # results at the 25-Sep-2026 cut-off
│   ├── cumulative_summary.csv        # preserved activity and gap decomposition, M1–M5
│   ├── weekly_indicators.csv         # weekly actual vs reference by group × segment
│   ├── validation.csv                # PortWatch vs DP World, AD Ports, Gulftainer
│   ├── backtest_wape.csv             # out-of-sample test of the baselines
│   ├── alerts.csv · hormuz_weekly.csv · monthly_east_oman.csv
│   └── powerbi/ZeroHormuz_PowerBI.xlsx   # star-schema tables feeding the dashboard
├── powerbi/
│   ├── ZeroHormuz_Monitor.pbix       # ready to open (data included)
│   ├── ZeroHormuz_Monitor_PBIP.zip   # full Power BI Project (PBIR report + TMDL model)
│   ├── ZeroHormuz_theme.json         # report theme
│   └── semantic-model/               # TMDL: model, relationships, tables and measures
└── docs/
    ├── ZeroHormuz_Monitor_v0.3.pdf
    └── images/                       # page screenshots
```

## How to reproduce

```bash
git clone https://github.com/mhzamx/zero-hormuz-monitor.git
cd zero-hormuz-monitor
pip install -r requirements.txt
python src/zero_hormuz_monitor.py --refresh --powerbi
```

- `--refresh` downloads fresh data from PortWatch into `data/` (PortWatch updates weekly, on Tuesdays). Later runs without it reuse the cached CSVs.
- `--powerbi` also writes `outputs/powerbi/ZeroHormuz_PowerBI.xlsx`.
- Running the script on the 3-Oct-2026 download reproduces the files in `outputs/` exactly.

**Power BI.** Open `powerbi/ZeroHormuz_Monitor.pbix` with Power BI Desktop. To work with the project version, unzip `ZeroHormuz_Monitor_PBIP.zip`, open the `.pbip` file, point each table's source in Power Query to your copy of `ZeroHormuz_PowerBI.xlsx`, and refresh.

## Tools

Python (pandas, NumPy, requests) · SQLite · Excel · Power BI Desktop (Power Query, DAX, star schema, PBIP / TMDL / PBIR) · IMF PortWatch API

## Sources

- **Volumes and transits:** [IMF PortWatch](https://portwatch.imf.org) (AIS-based estimates).
- **Validation:** DP World H1 2026 results; AD Ports Q2 2026 results; Gulftainer figures reported by The National (7 Jul 2026).
- **Capacities:** DP World (Jebel Ali), Gulftainer (Khor Fakkan), Port of Fujairah / AD Ports (Fujairah).
- **Context:** The National, WorldCargo News, AGBI, Nautica / Portcast.

This is an independent analysis. It is not affiliated with or endorsed by the IMF or any port operator, and all PortWatch figures are estimates.

## Author

**Miguel Ángel Hernández Aranda** · Data analyst, logistics and supply chain<br>
GitHub [@mhzamx](https://github.com/mhzamx) · mhzamx@outlook.com
