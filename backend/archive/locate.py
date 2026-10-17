"""Turn extracted archive entries into mapped occurrences (GeoJSON).

    python -m archive.locate out/archive/4506/pages.jsonl --out out/archive/4506

Each entry is placed by, in order of preference:
1. coordinates printed in the report;
2. a name match with a site already in the occurrence database (USGS), taking its
   coordinates and noting the match;
3. the centre of the smallest map sheet the report gives for it, with the sheet's
   half-diagonal as the location uncertainty.
Name matches are only made against sites inside the area the report covers (its
map sheets, plus a margin). Entries that none of these place go to unlocated.json for review against the report's
maps. Duplicate entries (the same name on several pages) are merged.
"""

import argparse
import difflib
import json
import re
from pathlib import Path

from app.data import load_occurrences

from .sheets import sheet_bbox

KIND_TO_TYPE = {"deposit": "deposit", "occurrence": "occurrence", "mineralization_point": "showing"}
# Generic words that differ between sources but do not identify the site.
GENERIC = {"proyavlenie", "proyavleniya", "uchastok", "mestorozhdenie", "gol", "uul", "ula", "nuur", "nur",
           "khudag", "khudog", "deposit", "occurrence", "prospect", "area", "site", "ii", "i", "1", "2"}
TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya", "ө": "o", "ү": "u",
})
MATCH_THRESHOLD = 0.82
# A match across different commodities needs a near-identical name, and is flagged.
CONFLICT_THRESHOLD = 0.95


def name_key(name: str) -> str:
    s = re.sub(r"\(.*?\)", " ", name).lower().translate(TRANSLIT)
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in GENERIC]
    s = "".join(words)
    # Collapse spelling variants common between Russian and English romanisations.
    for a, b in (("kh", "h"), ("yo", "e"), ("iy", "i"), ("yi", "i"), ("y", "i"), ("oo", "o"), ("uu", "u")):
        s = s.replace(a, b)
    return s


def best_match(entry: dict, known) -> tuple[object, float]:
    """Best-scoring known site by name, discounting matches that share no commodity."""
    keys = {name_key(entry["name_original"]), name_key(entry["name_latin"])} - {""}
    best, score = None, 0.0
    mine = set(entry["commodities"])
    for occ in known:
        k = name_key(occ.name)
        if not k:
            continue
        s = max(difflib.SequenceMatcher(None, k, q).ratio() for q in keys) if keys else 0.0
        # A similar name with no shared commodity is usually a different site.
        if mine and not mine & set(occ.commodities) and s < CONFLICT_THRESHOLD:
            s = 0.0
        if s > score:
            best, score = occ, s
    return best, score


def locate(entries: list[dict], known, bbox=None) -> tuple[list[dict], list[dict]]:
    features, unlocated = [], []
    merged: dict[str, dict] = {}
    for e in entries:
        key = name_key(e["name_latin"] or e["name_original"]) or e["name_original"]
        if key in merged:
            m = merged[key]
            m["pages"] = sorted(set(m["pages"]) | set(e["pages"]))
            for f in ("map_sheet", "map_number", "host_rocks", "alteration", "location_text"):
                m[f] = m[f] or e[f]
            m["commodities"] += [c for c in e["commodities"] if c not in m["commodities"]]
            m["assays"] += e["assays"]
            if m["latitude"] is None:
                m["latitude"], m["longitude"] = e["latitude"], e["longitude"]
        else:
            merged[key] = {**e, "commodities": list(e["commodities"]), "assays": list(e["assays"])}

    for i, e in enumerate(merged.values(), start=1):
        lat = lon = None
        how, precision, match = "", None, None
        if e["latitude"] is not None and e["longitude"] is not None:
            lat, lon, how, precision = e["latitude"], e["longitude"], "printed coordinates", 0.5
        else:
            occ, score = best_match(e, known)
            if occ is not None and score >= MATCH_THRESHOLD:
                lat, lon, how, precision = occ.lat, occ.lon, f"name match with {occ.id} ({occ.name})", 3.0
                match = {"id": occ.id, "name": occ.name, "score": round(score, 2),
                         "commodities": list(occ.commodities),
                         "commodity_conflict": bool(e["commodities"]) and not set(e["commodities"]) & set(occ.commodities)}
            elif e["map_sheet"]:
                try:
                    box = sheet_bbox(e["map_sheet"])
                    lat, lon = box.centre
                    how, precision = f"centre of sheet {e['map_sheet']}", round(box.half_diagonal_km, 1)
                except ValueError:
                    pass
        if lat is None or (bbox and not (bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3])):
            unlocated.append(e)
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "id": f"SOV-{e['report']}-{i}",
                "name": e["name_latin"] or e["name_original"],
                "name_original": e["name_original"],
                "commodities": e["commodities"],
                "type": KIND_TO_TYPE.get(e["kind"], "showing"),
                "source": f"Soviet archive report {e['report']}, p. {', '.join(map(str, e['pages']))}",
                "synthetic": False,
                "located_by": how,
                "location_uncertainty_km": precision,
                "usgs_match": match,
                "minerals": e["minerals"],
                "host_rocks": e["host_rocks"],
                "alteration": e["alteration"],
                "assays": e["assays"],
                "map_sheet": e["map_sheet"],
                "map_number": e["map_number"],
                "report_section": e["report_section"],
            },
        })
    return features, unlocated


def report_extent(pages_jsonl: Path, margin: float = 0.25):
    """(south, west, north, east) covering every sheet the report lists, plus a margin."""
    boxes = []
    for line in pages_jsonl.read_text(encoding="utf-8").splitlines():
        for sheet in json.loads(line)["map_sheets"] if line.strip() else []:
            try:
                boxes.append(sheet_bbox(sheet))
            except ValueError:
                pass
    if not boxes:
        return None
    return (min(b.south for b in boxes) - margin, min(b.west for b in boxes) - margin,
            max(b.north for b in boxes) + margin, max(b.east for b in boxes) + margin)


def load_entries(pages_jsonl: Path) -> list[dict]:
    out = []
    for line in pages_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        page = json.loads(line)
        for occ in page["occurrences"]:
            if occ["kind"] in KIND_TO_TYPE:
                out.append({**occ, "report": page["report"], "pages": [page["page"]]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", type=Path, help="pages.jsonl from archive.extract")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    extent = report_extent(args.pages)
    known = load_occurrences()
    if extent:
        # Only match names against sites inside the report's area: names repeat across Mongolia.
        s, w, n, e = extent
        known = tuple(o for o in known if s <= o.lat <= n and w <= o.lon <= e)
    features, unlocated = locate(load_entries(args.pages), known, extent)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "occurrences.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=1))
    (args.out / "unlocated.json").write_text(json.dumps(unlocated, ensure_ascii=False, indent=1))
    by = {}
    for f in features:
        by[f["properties"]["located_by"].split(" ")[0]] = by.get(f["properties"]["located_by"].split(" ")[0], 0) + 1
    print(f"{len(features)} located ({by}), {len(unlocated)} unlocated")


if __name__ == "__main__":
    main()
