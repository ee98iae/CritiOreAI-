"""Convert the USGS Northeast Asia lode deposit table into the GeoJSON format the API reads.

Source: Ariunbileg and others, 2003, Significant metalliferous and selected
non-metalliferous lode deposits, and selected placer districts of Northeast Asia,
USGS Open-File Report 03-220 (https://pubs.usgs.gov/of/2003/of03-220/).

1. Download DATABASE/lode_deposits.txt from the report into data/raw/neasia/.
2. python -m scripts.import_neasia data/raw/neasia/lode_deposits.txt > data/occurrences_neasia_mongolia.geojson

Only Mongolian deposits are kept, unless --all is given.
"""

import argparse
import json
import re
import sys

# Columns of lode_deposits.txt (tab-separated, no header row).
SHEET, MAP_NO, DEP_NO, NAME, LAT, LON = 0, 1, 2, 3, 5, 7
MAJOR, SIZE, COUNTRY = 8, 11, 16

# "Large"/"Medium" are significant deposits; "Small" and "Unknown" weigh less in scoring.
SIZE_TYPE = {"large": "deposit", "medium": "deposit", "small": "occurrence", "unknown": "occurrence"}


def commodities(major: str) -> list[str]:
    """'Au(Cu,Fe)', 'REE-Zr-Ta' or 'Cu, Mo' -> list of symbols, in order, without repeats."""
    out = []
    for token in re.split(r"[,()\-\s]+", major):
        if token and token not in out:
            out.append(token)
    return out


def rows(path: str):
    with open(path, encoding="latin-1", newline="") as f:
        for line in f.read().replace("\r\n", "\n").split("\n"):
            if line.strip():
                yield [c.strip() for c in line.split("\t")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("txt_path")
    ap.add_argument("--all", action="store_true", help="keep deposits outside Mongolia")
    args = ap.parse_args()

    features = []
    seen: set[str] = set()
    for r in rows(args.txt_path):
        if not args.all and r[COUNTRY] != "Mongolia":
            continue
        try:
            lat, lon = float(r[LAT]), float(r[LON])
        except (IndexError, ValueError):
            continue
        # The source reuses a few sheet/map/deposit numbers for different sites.
        base = dep_id = f"NEA-{r[SHEET]}{r[MAP_NO]}-{r[DEP_NO]}"
        n = 1
        while dep_id in seen:
            n += 1
            dep_id = f"{base}-{n}"
        seen.add(dep_id)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": {
                "id": dep_id,
                "name": r[NAME] or "Unnamed",
                "commodities": commodities(r[MAJOR]),
                "type": SIZE_TYPE.get(r[SIZE].lower(), "occurrence"),
                "source": "USGS Northeast Asia deposits (OFR 03-220)",
                "synthetic": False,
            },
        })
    print(f"kept {len(features)} deposits", file=sys.stderr)
    json.dump({"type": "FeatureCollection", "features": features}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
