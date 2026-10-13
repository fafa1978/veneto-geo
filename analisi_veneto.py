"""Analisi dei comuni del Veneto con GeoPandas, su confini ISTAT 2026 (CC-BY 4.0).

Uso:
    python -m pip install -r requirements.txt
    python analisi_veneto.py
"""
import io
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

ISTAT_URL = (
    "https://www.istat.it/storage/cartografia/confini_amministrativi/"
    "generalizzati/2026/Limiti01012026_g.zip"
)
COD_REG_VENETO = 5
PRO_COM_VENEZIA = 27042
CRS_METRICO = 32632  # UTM 32N, in metri
RAGGI_KM = [30, 60, 90]

BASE = Path(__file__).parent
DATA = BASE / "data"
OUT = BASE / "output"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)


def scarica_confini():
    if (DATA / "Com01012026_g").exists():
        return
    print("Scarico i confini ISTAT (circa 10 MB)...")
    req = Request(ISTAT_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=120) as r:
        zipfile.ZipFile(io.BytesIO(r.read())).extractall(DATA)


def carica_dati():
    comuni = gpd.read_file(
        DATA / "Com01012026_g" / "Com01012026_g_WGS84.shp", encoding="utf-8"
    )
    province = gpd.read_file(
        DATA / "ProvCM01012026_g" / "ProvCM01012026_g_WGS84.shp", encoding="utf-8"
    )
    comuni = comuni[comuni["COD_REG"] == COD_REG_VENETO].copy()
    province = province[province["COD_REG"] == COD_REG_VENETO].copy()
    return comuni.to_crs(CRS_METRICO), province.to_crs(CRS_METRICO)


def main():
    scarica_confini()
    comuni, province = carica_dati()

    prov_info = province[["COD_PROV", "DEN_UTS", "SIGLA"]].rename(
        columns={"DEN_UTS": "PROVINCIA"}
    )
    comuni = comuni.merge(prov_info, on="COD_PROV", how="left")

    comuni["area_km2"] = comuni.geometry.area / 1e6
    comuni["centroide"] = comuni.geometry.centroid

    venezia = comuni.loc[comuni["PRO_COM"] == PRO_COM_VENEZIA, "centroide"].iloc[0]
    comuni["dist_venezia_km"] = comuni["centroide"].distance(venezia) / 1000

    riepilogo = pd.DataFrame(
        [
            {"raggio_km": r, "comuni_dentro": int((comuni["dist_venezia_km"] <= r).sum())}
            for r in RAGGI_KM
        ]
    )
    print("\nComuni entro il raggio da Venezia (centroidi):")
    print(riepilogo.to_string(index=False))

    per_prov = (
        comuni.groupby("PROVINCIA")
        .agg(
            n_comuni=("COMUNE", "count"),
            area_tot_km2=("area_km2", "sum"),
            area_media_km2=("area_km2", "mean"),
        )
        .round(1)
        .sort_values("n_comuni", ascending=False)
    )
    print("\nStatistiche per provincia:")
    print(per_prov.to_string())

    cols = ["COMUNE", "PROVINCIA", "area_km2", "dist_venezia_km"]
    piu_grandi = comuni.nlargest(10, "area_km2")[cols].round(1)
    piu_piccoli = comuni.nsmallest(10, "area_km2")[cols].round(1)
    print("\n10 comuni piu' estesi:\n", piu_grandi.to_string(index=False))
    print("\n10 comuni meno estesi:\n", piu_piccoli.to_string(index=False))

    export = comuni.drop(columns=["centroide"]).to_crs(4326)
    export.to_file(OUT / "comuni_veneto.geojson", driver="GeoJSON")
    pd.concat(
        [piu_grandi.assign(tipo="piu_esteso"), piu_piccoli.assign(tipo="meno_esteso")]
    ).to_csv(OUT / "classifiche_comuni.csv", index=False)
    per_prov.to_csv(OUT / "statistiche_province.csv")

    fig, ax = plt.subplots(figsize=(9, 9))
    comuni.plot(
        column="area_km2", cmap="YlGnBu", scheme="quantiles", k=6,
        legend=True, linewidth=0.15, edgecolor="white", ax=ax,
        legend_kwds={"title": "Superficie (km²)", "loc": "upper left"},
    )
    province.boundary.plot(ax=ax, color="black", linewidth=0.8)
    ax.set_title("Comuni del Veneto per superficie (dati ISTAT 2026)")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(OUT / "mappa_superficie.png", dpi=170)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 9))
    comuni.plot(
        column="dist_venezia_km", cmap="viridis_r", legend=True,
        linewidth=0.15, edgecolor="white", ax=ax,
        legend_kwds={"label": "Distanza dal centroide di Venezia (km)",
                     "shrink": 0.6},
    )
    anelli = gpd.GeoSeries(
        [venezia.buffer(r * 1000) for r in RAGGI_KM], crs=CRS_METRICO
    )
    anelli.boundary.plot(ax=ax, color="red", linewidth=1, linestyle="--")
    gpd.GeoSeries([venezia], crs=CRS_METRICO).plot(ax=ax, color="red", markersize=40)
    for r, geom in zip(RAGGI_KM, anelli):
        x, y = geom.exterior.coords[0]
        ax.annotate(f"{r} km", (x, y), color="red", fontsize=9)
    ax.set_title("Distanza dei comuni veneti da Venezia")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(OUT / "mappa_distanza_venezia.png", dpi=170)
    plt.close(fig)

    print(f"\nFatto. File salvati in: {OUT}")


if __name__ == "__main__":
    main()
