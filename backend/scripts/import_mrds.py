"""Convert a USGS MRDS CSV export into the GeoJSON format the API reads.

1. Download MRDS (https://mrdata.usgs.gov/mrds/) as CSV, or a filtered export
   for Mongolia.
2. python -m scripts.import_mrds mrds.csv > data/occurrences_mrds.geojson
   (or point CRITIORE_OCCURRENCES at the output file).

Only sites inside the pilot region bbox are kept, unless --all is given.
"""

import argparse
import csv
import json
import sys

from app.regions import PILOT_REGION

SYMBOLS = {
    "copper": "Cu", "nickel": "Ni", "cobalt": "Co", "gold": "Au", "molybdenum": "Mo",
    "silver": "Ag", "zinc": "Zn", "lead": "Pb", "tungsten": "W", "tin": "Sn",
    "iron": "Fe", "uranium": "U", "platinum": "Pt", "palladium": "Pd", "lithium": "Li",
    "rare earth elements": "REE", "fluorine-fluorite": "F", "coal": "Coal",
}
DEV_STAT_TYPE = {"producer": "deposit", "past producer": "deposit", "prospect": "occurrence",
                 "occurrence": "showing"}


def commodities(row: dict) -> list[str]:
    out = []
    for key in ("commod1", "commod2", "commod3"):
        for name in (row.get(key) or "").split(","):
            name = name.strip().lower()
            if name and (sym := SYMBOLS.get(name, name.title())) not in out:
                out.append(sym)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--all", action="store_true", help="keep sites outside the pilot region")
    args = ap.parse_args()

    south, west, north, east = PILOT_REGION.bbox
    features = []
    with open(args.csv_path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
            except (KeyError, ValueError):
                continue
            if not args.all and not (south <= lat <= north and west <= lon <= east):
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": f"MRDS-{row.get('dep_id', len(features))}",
                    "name": row.get("site_name") or "Unnamed",
                    "commodities": commodities(row),
                    "type": DEV_STAT_TYPE.get((row.get("dev_stat") or "").lower(), "showing"),
                    "source": "USGS MRDS",
                    "synthetic": False,
                },
            })
    print(f"kept {len(features)} sites", file=sys.stderr)
    json.dump({"type": "FeatureCollection", "features": features}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
