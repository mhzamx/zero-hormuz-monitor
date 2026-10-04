"""
Zero Hormuz Monitor v0.3 — UAE Data Impact Project 2026
Reproducible pipeline: IMF PortWatch -> SQLite -> weekly indicators (Biblia v2.1, section 11).

Usage:
    python zero_hormuz_monitor.py --refresh      # download fresh data from PortWatch, then compute
    python zero_hormuz_monitor.py                # reuse cached CSVs in data/, then compute
    python zero_hormuz_monitor.py --powerbi      # also export the Power BI package (outputs/powerbi/)

Outputs (folder outputs/):
    weekly_indicators.csv     weekly actual vs reference (M3 main; M1, M4 sensitivity) by group x segment
    cumulative_summary.csv    cumulative since 2026-03-01: preserved activity, gap decomposition, IDO
    monthly_east_oman.csv     monthly totals for East coast and Oman (reported monthly, Biblia rule)
    alerts.csv                weekly port spikes (> rolling median + 3 MAD) and tonnes-per-call jumps
    validation.csv            YoY checks vs official figures (DP World, AD Ports, Gulftainer)
    backtest_wape.csv         out-of-sample backtest of reference methods (no future information)
    hormuz_weekly.csv         weekly cargo-vessel transits registered by AIS (PortWatch)
    powerbi/                  star-schema tables (CSV) + ZeroHormuz_PowerBI.xlsx for Power BI (with --powerbi)
                              v0.3 adds porque_semanal + porque_capacidad ("¿Por qué no reemplazan?" page)
Definitions: see 00 — BIBLIA MAESTRA v2.1, section 11. All PortWatch figures are estimates.
"""
import argparse, datetime as dt, glob, os, sqlite3
import numpy as np, pandas as pd, requests

BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
SHOCK = pd.Timestamp("2026-02-28")
START = pd.Timestamp("2026-03-01")
PORTS = {  # portid: (name, group)
    "port744": ("Jebel Ali", "Golfo EAU"), "port2025": ("Khalifa Port", "Golfo EAU"),
    "port5": ("Abu Dhabi", "Golfo EAU"), "port306": ("Dubai", "Golfo EAU"), "port72": ("Sharjah", "Golfo EAU"),
    "port13": ("Ajman", "Golfo EAU"), "port1340": ("Umm al Qaiwain", "Golfo EAU"), "port747": ("Mina Saqr", "Golfo EAU"),
    "port22": ("Al Hamriyah LPG Terminal", "Golfo EAU"), "port512": ("Jabal Az Zannah-Ruways", "Golfo EAU"),
    "port2236": ("Jebel Dhanna", "Golfo EAU"), "port2237": ("Das Island", "Golfo EAU"), "port2235": ("Zirku Island", "Golfo EAU"),
    "port362": ("Fujairah", "Costa este EAU"), "port561": ("Khor Fakkan", "Costa este EAU"),
    "port988": ("Port of Sohar", "Omán"), "port746": ("Salalah", "Omán"), "port984": ("Duqm", "Omán"),
}
SEGMENTS = {
    "Contenedores": ["container"], "Carga general + RoRo": ["general_cargo", "roro"], "Granel seco": ["dry_bulk"],
    "Tanqueros": ["tanker"], "No tanqueros": ["container", "general_cargo", "roro", "dry_bulk"],
    "Total": ["container", "general_cargo", "roro", "dry_bulk", "tanker"],
}
GROUPS = ["Golfo EAU", "Costa este EAU", "Omán"]
OUT, DATA = "outputs", "data"


def fetch(svc, where):
    rows, off = [], 0
    while True:
        p = dict(where=where, outFields="*", returnGeometry="false", f="json",
                 resultOffset=off, resultRecordCount=2000, orderByFields="ObjectId")
        r = requests.get(f"{BASE}/{svc}/FeatureServer/0/query", params=p, timeout=180)
        r.raise_for_status(); d = r.json()
        if "error" in d: raise RuntimeError(d["error"])
        fs = [f["attributes"] for f in d.get("features", [])]; rows += fs
        if not d.get("exceededTransferLimit") and len(fs) < 2000: break
        off += len(fs)
    return pd.DataFrame(rows)


def load(refresh):
    os.makedirs(DATA, exist_ok=True)
    if refresh or not glob.glob(f"{DATA}/ports_daily_*.csv"):
        stamp = dt.date.today().isoformat()
        plist = "(" + ",".join(f"'{p}'" for p in PORTS) + ")"
        fetch("Daily_Ports_Data", f"portid IN {plist} AND year>=2019").to_csv(f"{DATA}/ports_daily_{stamp}.csv", index=False)
        fetch("Daily_Chokepoints_Data", "portid='chokepoint6' AND year>=2019").to_csv(f"{DATA}/hormuz_daily_{stamp}.csv", index=False)
        fetch("PortWatch_ports_database", f"portid IN {plist}").to_csv(f"{DATA}/ports_catalog_{stamp}.csv", index=False)
    dp = pd.read_csv(sorted(glob.glob(f"{DATA}/ports_daily_*.csv"))[-1])
    hz = pd.read_csv(sorted(glob.glob(f"{DATA}/hormuz_daily_*.csv"))[-1])
    for df in (dp, hz):
        df["d"] = pd.to_datetime(dict(year=df.year, month=df.month, day=df.day))
    dp["grupo"] = dp.portid.map(lambda p: PORTS[p][1])
    for s, cols in SEGMENTS.items():
        dp["t_" + s] = sum(dp[f"import_{c}"] + dp[f"export_{c}"] for c in cols)
        dp["c_" + s] = sum(dp[f"portcalls_{c}"] for c in cols)
    return dp, hz


def to_sqlite(dp, hz):
    con = sqlite3.connect(f"{OUT}/zero_hormuz.sqlite")
    dp.drop(columns=["d"]).assign(date=dp.d.dt.date.astype(str)).to_sql("ports_daily", con, if_exists="replace", index=False)
    hz.drop(columns=["d"]).assign(date=hz.d.dt.date.astype(str)).to_sql("chokepoints_daily", con, if_exists="replace", index=False)
    pd.DataFrame([(k, v[0], v[1]) for k, v in PORTS.items()], columns=["portid", "portname", "grupo"]).to_sql("ports_catalog", con, if_exists="replace", index=False)
    con.close()


def reference(x, method, origin=SHOCK):
    """x: daily series (DatetimeIndex, daily freq). Returns reference series using only info allowed by the method."""
    lag1, lag2 = x.shift(364), x.shift(728)
    if method == "M1": return lag1
    if method == "M3": return (lag1 + lag2) / 2
    if method == "M4": return pd.Series(x[:origin][-56:].mean(), index=x.index)
    def factor(base):  # growth factor from the 8 weeks before origin; undefined if the base is zero
        den = base[:origin][-56:].sum()
        return x[:origin][-56:].sum() / den if den > 0 else np.nan
    if method == "M2": return lag1 * factor(lag1)
    if method == "M5":
        m3 = (lag1 + lag2) / 2; return m3 * factor(m3)
    raise ValueError(method)


def daily_group(dp):
    cols = [f"t_{s}" for s in SEGMENTS] + [f"c_{s}" for s in SEGMENTS]
    return {g: dp[dp.grupo == g].groupby("d")[cols].sum().asfreq("D") for g in GROUPS}


def weekly_indicators(G):
    rows = []
    for s in SEGMENTS:
        for m in ["M3", "M1", "M4"]:
            act = {g: G[g][f"t_{s}"] for g in GROUPS}
            ref = {g: reference(act[g], m) for g in GROUPS}
            wk = lambda z: z[START:].resample("W-SUN").sum()
            A = {g: wk(act[g]) for g in GROUPS}; R = {g: wk(ref[g]) for g in GROUPS}
            for w in A["Golfo EAU"].index:
                ga, gr, ea, er, oa, orf = (A["Golfo EAU"][w], R["Golfo EAU"][w], A["Costa este EAU"][w],
                                           R["Costa este EAU"][w], A["Omán"][w], R["Omán"][w])
                rows.append(dict(semana_fin=w.date(), segmento=s, referencia=m, golfo_act_t=ga, golfo_ref_t=gr,
                                 este_act_t=ea, este_ref_t=er, oman_act_t=oa, oman_ref_t=orf,
                                 preservada_pct=100 * (ga + ea) / (gr + er) if (gr + er) else np.nan,
                                 perdida_golfo_t=gr - ga, cambio_este_t=ea - er, brecha_t=(gr + er) - (ga + ea),
                                 ido_pct=100 * ga / (ga + ea) if (ga + ea) else np.nan,
                                 dias=int(min(7, (min(w, act["Golfo EAU"].index.max()) - max(w - pd.Timedelta(days=6), START)).days + 1))))
    return pd.DataFrame(rows)


def cumulative(G, end):
    rows = []
    for s in SEGMENTS:
        for m in ["M1", "M2", "M3", "M4", "M5"]:
            A = {g: G[g][f"t_{s}"][START:end].sum() / 1e6 for g in GROUPS}
            R = {g: reference(G[g][f"t_{s}"], m)[START:end].sum(min_count=1) / 1e6 for g in GROUPS}
            if any(pd.isna(v) for v in R.values()): continue  # reference undefined (e.g. zero base for growth factor)
            ce = A["Costa este EAU"] - R["Costa este EAU"]
            rows.append(dict(segmento=s, referencia=m, periodo=f"{START.date()} a {end.date()}",
                             golfo_ref_Mt=R["Golfo EAU"], golfo_act_Mt=A["Golfo EAU"], este_ref_Mt=R["Costa este EAU"], este_act_Mt=A["Costa este EAU"],
                             a_perdida_golfo_Mt=R["Golfo EAU"] - A["Golfo EAU"], b_compensacion_este_Mt=max(ce, 0), b_perdida_propia_este_Mt=max(-ce, 0),
                             c_oman_acreditado_Mt=0.0, oman_dif_no_acreditada_Mt=A["Omán"] - R["Omán"],
                             d_brecha_residual_Mt=(R["Golfo EAU"] + R["Costa este EAU"]) - (A["Golfo EAU"] + A["Costa este EAU"]),
                             preservada_pct=100 * (A["Golfo EAU"] + A["Costa este EAU"]) / (R["Golfo EAU"] + R["Costa este EAU"]),
                             ido_ref_pct=100 * R["Golfo EAU"] / (R["Golfo EAU"] + R["Costa este EAU"]),
                             ido_act_pct=100 * A["Golfo EAU"] / (A["Golfo EAU"] + A["Costa este EAU"]),
                             compensacion_pct_de_perdida=100 * max(ce, 0) / (R["Golfo EAU"] - A["Golfo EAU"])))
    return pd.DataFrame(rows)


def monthly_east_oman(dp):
    m = dp[dp.grupo.isin(["Costa este EAU", "Omán"]) & (dp.d >= "2025-01-01")].copy()
    m["mes"] = m.d.dt.to_period("M").astype(str)
    cols = [f"t_{s}" for s in SEGMENTS] + [f"c_{s}" for s in SEGMENTS]
    return m.groupby(["mes", "grupo", "portname"])[cols].sum().reset_index()


def alerts(dp):
    out = []
    for p, g in dp.groupby("portname"):
        w = g.set_index("d")[["t_Total", "c_Total"]].resample("W-SUN").sum()
        med = w.t_Total.rolling(26, min_periods=12).median().shift(1)
        mad = (w.t_Total - med).abs().rolling(26, min_periods=12).median().shift(1)
        tpc = (w.t_Total / w.c_Total.replace(0, np.nan))
        tpc_med = tpc.rolling(26, min_periods=12).median().shift(1)
        for d in w.index[w.index >= "2025-01-01"]:
            if pd.notna(mad[d]) and mad[d] > 0 and w.t_Total[d] > med[d] + 3 * mad[d]:
                out.append(dict(semana_fin=d.date(), puerto=p, tipo="pico de toneladas", valor_t=w.t_Total[d], mediana_previa_t=med[d]))
            if pd.notna(tpc_med[d]) and pd.notna(tpc[d]) and tpc[d] > 3 * tpc_med[d]:
                out.append(dict(semana_fin=d.date(), puerto=p, tipo="salto de toneladas por escala", valor_t=tpc[d], mediana_previa_t=tpc_med[d]))
    return pd.DataFrame(out)


def validation(dp):
    dp = dp.copy(); dp["q"] = dp.d.dt.quarter
    def yoy(ports, q=None, h1=False):
        sub = dp[dp.portname.isin(ports) & (dp.year.isin([2025, 2026]))]
        sub = sub[sub.q <= 2] if h1 else sub[sub.q == q]
        s = sub.groupby("year")["t_Contenedores"].sum()
        return 100 * (s[2026] / s[2025] - 1)
    rows = [
        dict(prueba="Jebel Ali, contenedores, Q2 2026 a/a", portwatch=yoy(["Jebel Ali"], 2), oficial=-90.1, fuente_oficial="DP World H1 2026 (S27)", unidad="toneladas vs TEU (variación %)"),
        dict(prueba="Jebel Ali, contenedores, H1 2026 a/a", portwatch=yoy(["Jebel Ali"], h1=True), oficial=-59.5, fuente_oficial="DP World H1 2026 (S27)", unidad="toneladas vs TEU (variación %)"),
        dict(prueba="Khalifa+Fujairah+Abu Dhabi, contenedores, Q2 2026 a/a", portwatch=yoy(["Khalifa Port", "Fujairah", "Abu Dhabi"], 2), oficial=-65.0, fuente_oficial="AD Ports Q2 2026 (S28); conjuntos distintos", unidad="toneladas vs TEU (variación %)"),
    ]
    kf = dp[dp.portname == "Khor Fakkan"].set_index("d")["t_Contenedores"].resample("W-SUN").sum()
    ratio = kf["2026-06-15":"2026-07-12"].mean() / kf["2025"].mean()
    rows.append(dict(prueba="Khor Fakkan, contenedores, jun-jul 2026 vs promedio 2025 (múltiplo)", portwatch=ratio, oficial=65000 / 8000,
                     fuente_oficial="Gulftainer vía The National 7-jul-2026 (S36)", unidad="múltiplo (toneladas vs TEU)"))
    v = pd.DataFrame(rows); v["diferencia"] = v.portwatch - v.oficial
    return v


def backtest(G):
    wins = {"A: mar-sep 2024": ("2024-02-29", "2024-03-01", "2024-09-25"), "B: mar-sep 2025": ("2025-02-28", "2025-03-01", "2025-09-25"),
            "C: dic 2025-feb 2026": ("2025-11-30", "2025-12-01", "2026-02-22")}
    out = []
    for g in GROUPS:
        for s in ["Contenedores", "No tanqueros", "Tanqueros", "Total"]:
            x = G[g][f"t_{s}"]
            for wn, (o, a, b) in wins.items():
                act = x[a:b].resample("W-SUN").sum()
                for m in ["M1", "M2", "M3", "M4", "M5"]:
                    pr = reference(x, m, origin=pd.Timestamp(o))[a:b].resample("W-SUN").sum()
                    out.append(dict(grupo=g, segmento=s, ventana=wn, metodo=m, WAPE_pct=100 * (act - pr).abs().sum() / act.sum(),
                                    sesgo_pct=100 * (pr.sum() / act.sum() - 1)))
    return pd.DataFrame(out)


BASE_SEGMENTS = ["Contenedores", "Carga general + RoRo", "Granel seco", "Tanqueros"]
RESUMEN_SEGMENTS = BASE_SEGMENTS + ["No tanqueros", "Total"]  # orden de la tabla puente dim_segmento_resumen


def mso_table(dp):
    """Movimiento sostenido observado: max 4-week rolling mean of weekly tonnes after the shock, per port and segment."""
    rows = []
    for (p, g), sub in dp.groupby(["portname", "grupo"]):
        for s in BASE_SEGMENTS + ["Total"]:
            w = sub.set_index("d")[f"t_{s}"].resample("W-SUN").sum()
            r4 = w.rolling(4).mean()
            post = r4[START + pd.Timedelta(days=27):]
            ref = w["2025-03-01":"2025-09-28"].mean()
            if post.empty: continue
            rows.append(dict(puerto=p, grupo=g, segmento=s, mso_t_semana=post.max(), semana_fin_mso=post.idxmax().date(),
                             promedio_semanal_mar_sep_2025_t=ref, mso_vs_2025=post.max() / ref if ref else np.nan,
                             ultimo_prom4_t_semana=r4.iloc[-1]))
    return pd.DataFrame(rows)


# v0.3 — "¿Por qué los puertos alternativos no reemplazan?"
# Capacidades OFICIALES de contenedores (millones de TEU al año). No salen de PortWatch: se capturan a mano con su fuente
# y fecha de consulta. Comparar capacidad con capacidad; nunca mezclar con toneladas AIS.
CAPACIDAD_OFICIAL = [
    # (puerto, grupo, capacidad_mteu, nota, fuente, url)
    ("Jebel Ali", "Golfo EAU", 19.4, "Capacidad instalada de contenedores; movió 15.5 M TEU en 2024", "DP World",
     "https://www.dpworld.com/en/news/dp-world-records-highest-cargo-volumes-at-jebel-ali-port-since-2015"),
    ("Khor Fakkan", "Costa este EAU", 5.0, "Capacidad tras la ampliación de 2026 (3.5 M TEU en jul-2026)", "Gulftainer; The National",
     "https://www.gulftainer.com/ports-terminals/khorfakkan-container-terminal/"),
    ("Fujairah", "Costa este EAU", 0.72, "Capacidad de contenedores (Fujairah Terminals)", "Puerto de Fujairah; AD Ports",
     "https://www.fujairahport.ae/about-us/port-of-fujairah-overview/"),
]
CAPACIDAD_CONSULTA = "2026-10-03"


def porque_semanal(dp, end):
    """Contenedores por semana (miles de t, AIS) en Jebel Ali, Khor Fakkan y Fujairah. Solo semanas completas (lun-dom)."""
    ids = {"port744": "jebel_ali", "port561": "khor_fakkan", "port362": "fujairah"}
    x = dp[dp.portid.isin(ids)].pivot_table(index="d", columns="portid", values="t_Contenedores", aggfunc="sum")
    w = x.asfreq("D").fillna(0).resample("W-SUN").sum().rename(columns=ids)
    w = w[(w.index >= "2025-01-01") & (w.index <= end)] / 1000  # la semana que termina después del corte es parcial: fuera
    out = pd.DataFrame({"semana": w.index.date,
                        "jebel_ali_cont_kt": w.jebel_ali.values, "khor_fakkan_cont_kt": w.khor_fakkan.values,
                        "khor_fakkan_prom4_kt": w.khor_fakkan.rolling(4).mean().values, "fujairah_cont_kt": w.fujairah.values,
                        "costa_este_cont_kt": (w.khor_fakkan + w.fujairah).values})
    return out.round(1)


def porque_capacidad():
    return pd.DataFrame([dict(puerto=p, grupo=g, capacidad_mteu=c, nota=n, fuente=f, url=u, consulta=CAPACIDAD_CONSULTA, orden=i + 1)
                         for i, (p, g, c, n, f, u) in enumerate(CAPACIDAD_OFICIAL)])


def powerbi_export(dp, hz, G, end):
    """Star schema for Power BI. All tonnes are PortWatch estimates (AIS)."""
    pb = f"{OUT}/powerbi"; os.makedirs(pb, exist_ok=True)
    cat_files = sorted(glob.glob(f"{DATA}/ports_catalog_*.csv"))
    cat = pd.read_csv(cat_files[-1])[["portid", "lat", "lon"]] if cat_files else pd.DataFrame(columns=["portid", "lat", "lon"])
    dim_p = pd.DataFrame([(k, v[0], v[1], "EAU" if v[1] != "Omán" else "Omán",
                           "Dentro de Ormuz (Golfo)" if v[1] == "Golfo EAU" else "Fuera de Ormuz (Golfo de Omán)") for k, v in PORTS.items()],
                         columns=["portid", "puerto", "grupo", "pais", "ubicacion"]).merge(cat, on="portid", how="left")
    dim_p["orden_grupo"] = dim_p.grupo.map({"Golfo EAU": 1, "Costa este EAU": 2, "Omán": 3})
    dim_s = pd.DataFrame({"segmento": BASE_SEGMENTS, "orden": [1, 2, 3, 4], "es_tanquero": [False, False, False, True],
                          "nota": ["Toneladas estimadas de buques portacontenedores", "Carga general y buques RoRo",
                                   "Graneleros secos", "Tanqueros (se reportan aparte en la Biblia)"]})
    days = pd.date_range("2025-01-01", max(end, hz.d.max()), freq="D")  # cubre también los tránsitos de Ormuz
    dim_f = pd.DataFrame({"fecha": days.date})
    dim_f["anio"] = days.year; dim_f["mes"] = days.month; dim_f["mes_nombre"] = days.strftime("%Y-%m")
    dim_f["trimestre"] = "T" + days.quarter.astype(str) + "-" + days.year.astype(str)
    dim_f["semana_fin_domingo"] = (days + pd.to_timedelta((6 - days.dayofweek) % 7, unit="D")).date
    dim_f["periodo"] = np.where(days >= START, "Choque (desde 1-mar-2026)", np.where(days >= SHOCK, "Choque", "Antes del choque"))
    dim_f["dias_desde_choque"] = (days - SHOCK).days
    rows = []
    for (pid, pname), sub in dp.groupby(["portid", "portname"]):
        sub = sub.set_index("d").asfreq("D")
        for s in BASE_SEGMENTS:
            cols = SEGMENTS[s]
            x = sub[f"t_{s}"].fillna(0)
            imp = sum(sub[f"import_{c}"] for c in cols).fillna(0); exp = sum(sub[f"export_{c}"] for c in cols).fillna(0)
            r3, r1, r4 = reference(x, "M3"), reference(x, "M1"), reference(x, "M4")
            c = sub[f"c_{s}"].fillna(0); c1 = c.shift(364); c3 = (c.shift(364) + c.shift(728)) / 2
            f = pd.DataFrame({"fecha": x.index.date, "portid": pid, "segmento": s, "toneladas_importacion": imp.values,
                              "toneladas_exportacion": exp.values, "toneladas": x.values, "ref_M3_t": r3.values,
                              "ref_M1_t": r1.values, "ref_M4_t": r4.values, "escalas": c.values, "ref_M3_escalas": c3.values,
                              "ref_M1_escalas": c1.values})
            rows.append(f[(f.fecha >= days[0].date()) & (f.fecha <= end.date())])
    fact = pd.concat(rows, ignore_index=True)
    hzd = hz[hz.d >= "2019-01-01"].set_index("d").asfreq("D")
    orm = pd.DataFrame({"fecha": hzd.index.date, "transitos_total": hzd.n_total.values, "tanqueros": hzd.n_tanker.values,
                        "contenedores": hzd.n_container.values, "granel_seco": hzd.n_dry_bulk.values,
                        "carga_general": hzd.n_general_cargo.values, "roro": hzd.n_roro.values})
    orm["ref_M3_transitos"] = (orm.transitos_total.shift(364) + orm.transitos_total.shift(728)) / 2
    orm = orm[orm.fecha >= days[0].date()]
    cum = cumulative(G, end)
    casc = []
    for s in RESUMEN_SEGMENTS:
        m = cum[(cum.segmento == s) & (cum.referencia == "M3")].iloc[0]
        for o, k, v in [(1, "Referencia (Golfo + costa este)", m.golfo_ref_Mt + m.este_ref_Mt), (2, "Pérdida del Golfo", -m.a_perdida_golfo_Mt),
                        (3, "Compensación de la costa este", m.b_compensacion_este_Mt), (4, "Pérdida propia de la costa este", -m.b_perdida_propia_este_Mt),
                        (5, "Omán acreditado (no identificado)", 0.0)]:
            casc.append(dict(segmento=s, orden=o, concepto=k, valor_Mt=round(float(v), 3) + 0.0))  # +0.0 elimina el -0.0
    dim_sr = pd.DataFrame({"segmento": RESUMEN_SEGMENTS, "orden": range(1, len(RESUMEN_SEGMENTS) + 1),
                           "tipo": ["Segmento"] * 4 + ["Agregado"] * 2})
    tables = {"dim_puerto": dim_p, "dim_segmento": dim_s, "dim_segmento_resumen": dim_sr, "dim_fecha": dim_f, "fact_puerto_diario": fact, "fact_ormuz_diario": orm,
              "resumen_acumulado": cum, "cascada_M3": pd.DataFrame(casc), "validacion": validation(dp), "backtest_wape": backtest(G),
              "alertas": alerts(dp), "mso_puertos": mso_table(dp),
              "porque_semanal": porque_semanal(dp, end), "porque_capacidad": porque_capacidad()}
    for k, t in tables.items(): t.to_csv(f"{pb}/{k}.csv", index=False, encoding="utf-8-sig")
    leeme = pd.DataFrame([
        ("Proyecto", "Zero Hormuz Monitor — UAE Data Impact Project 2026. Definiciones: Biblia v2.1, sección 11."),
        ("Fuente", "IMF PortWatch (datos abiertos, API ArcGIS). Todas las toneladas y escalas son ESTIMACIONES basadas en señales AIS."),
        ("Corte de datos", f"Puertos hasta {end.date()}; tránsitos de Ormuz hasta {hz.d.max().date()}."),
        ("fact_puerto_diario", "Una fila por fecha × puerto × segmento. toneladas = importación + exportación. ref_M3_t = promedio del mismo día de la semana 52 y 104 semanas antes (referencia principal); ref_M1_t = 52 semanas antes; ref_M4_t = nivel promedio de las 8 semanas previas al choque."),
        ("dim_puerto", "18 puertos: grupo Golfo EAU (13), Costa este EAU (2: Fujairah, Khor Fakkan), Omán (3, solo comparación)."),
        ("Actividad preservada", "SUM(toneladas) ÷ SUM(ref_M3_t) para Golfo EAU + Costa este EAU. No incluye Omán."),
        ("Brecha", "(Golfo ref − Golfo actual) − (costa este actual − costa este ref). Interpretación obligatoria: diferencia de actividad respecto de la referencia histórica; su recuperación y posible redistribución se evalúan mediante escenarios separados."),
        ("Omán", "Volumen atribuible no identificado; ninguna compensación acreditada (no reduce la brecha)."),
        ("resumen_acumulado", "Acumulado 1-mar-2026 al corte, por segmento y referencia (M1 a M5) para el rango de sensibilidad metodológica."),
        ("cascada_M3", "Tabla lista para el visual de cascada (waterfall) de Power BI, referencia M3, en millones de toneladas."),
        ("dim_segmento_resumen", "Tabla puente (6 filas: 4 segmentos + No tanqueros + Total) que filtra resumen_acumulado y cascada_M3."),
        ("mso_puertos", "Movimiento sostenido observado: máximo del promedio móvil de 4 semanas después del choque. No es capacidad."),
        ("validacion", "Variaciones de PortWatch contra cifras oficiales (DP World, AD Ports, Gulftainer). Nunca comparar niveles."),
        ("alertas", "Picos y saltos de toneladas por escala para investigar; no son errores confirmados."),
        ("porque_semanal", "v0.3. Contenedores por semana (miles de t, estimación AIS) en Jebel Ali, Khor Fakkan y Fujairah; solo semanas completas. khor_fakkan_prom4_kt = promedio móvil de 4 semanas."),
        ("porque_capacidad", "v0.3. Capacidad OFICIAL de contenedores (millones de TEU/año) con fuente y fecha de consulta. No es dato de PortWatch; no comparar con toneladas."),
    ], columns=["campo", "descripcion"])
    with pd.ExcelWriter(f"{pb}/ZeroHormuz_PowerBI.xlsx", engine="openpyxl") as xw:
        leeme.to_excel(xw, sheet_name="LEEME", index=False)
        for k, t in tables.items(): t.to_excel(xw, sheet_name=k[:31], index=False)
    return tables


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--refresh", action="store_true"); ap.add_argument("--powerbi", action="store_true"); a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    dp, hz = load(a.refresh); to_sqlite(dp, hz)
    G = daily_group(dp); end = dp.d.max()
    weekly_indicators(G).round(3).to_csv(f"{OUT}/weekly_indicators.csv", index=False)
    cumulative(G, end).round(3).to_csv(f"{OUT}/cumulative_summary.csv", index=False)
    monthly_east_oman(dp).round(1).to_csv(f"{OUT}/monthly_east_oman.csv", index=False)
    alerts(dp).round(1).to_csv(f"{OUT}/alerts.csv", index=False)
    validation(dp).round(2).to_csv(f"{OUT}/validation.csv", index=False)
    backtest(G).round(2).to_csv(f"{OUT}/backtest_wape.csv", index=False)
    hz.set_index("d")[["n_total", "n_tanker", "n_container", "n_dry_bulk", "n_general_cargo", "n_roro"]].resample("W-SUN").sum().to_csv(f"{OUT}/hormuz_weekly.csv")
    if a.powerbi: powerbi_export(dp, hz, G, end)
    print(f"Datos hasta {end.date()} | salidas en {OUT}/")


if __name__ == "__main__":
    main()
