import json

from app.data import DEFAULT_PATH, _parse
from app.regions import PILOT_REGION
from scripts.import_neasia import commodities


def test_neasia_commodity_parsing():
    assert commodities("Au(Cu,Fe)") == ["Au", "Cu", "Fe"]
    assert commodities("REE-Zr-Ta") == ["REE", "Zr", "Ta"]
    assert commodities("Cu, Mo, Cu") == ["Cu", "Mo"]


def test_default_dataset_is_real_and_covers_pilot():
    with DEFAULT_PATH.open(encoding="utf-8") as f:
        occs = [_parse(feat) for feat in json.load(f)["features"]]
    assert len(occs) > 100
    assert not any(o.synthetic for o in occs)
    assert len({o.id for o in occs}) == len(occs)
    south, west, north, east = PILOT_REGION.bbox
    pilot = [o for o in occs if south <= o.lat <= north and west <= o.lon <= east]
    assert sum("Cu" in o.commodities for o in pilot) >= 5
