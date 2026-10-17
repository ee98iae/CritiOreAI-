"""Archive digitiser: sheet geocoding, locating entries, and the extraction request."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.data import Occurrence
from archive.locate import locate, name_key
from archive.sheets import sheet_bbox


def test_sheet_bbox_follows_soviet_nomenclature():
    assert sheet_bbox("M-46") == sheet_bbox("М-46")  # Cyrillic М as scanned
    b = sheet_bbox("M-46").__dict__
    assert b == {"south": 48.0, "west": 90.0, "north": 52.0, "east": 96.0}
    b = sheet_bbox("M-46-86")
    assert (b.south, b.west, b.north, b.east) == pytest.approx((49 + 1 / 3, 90.5, 49 + 2 / 3, 91.0))
    b = sheet_bbox("M-46-100-Б")  # 1:50k, north-east quarter
    assert (b.south, b.west, b.north, b.east) == pytest.approx((49 + 1 / 6, 91.75, 49 + 1 / 3, 92.0))
    b = sheet_bbox("M-46-86-Б-в")  # 1:25k, south-west quarter of that
    assert (b.south, b.west) == pytest.approx((49.5, 90.75))
    with pytest.raises(ValueError):
        sheet_bbox("M-46-145")


def test_name_key_ignores_generic_words_and_romanisation():
    assert name_key("Участок Намирин") == name_key("Namiryn gol")
    assert name_key("Проявление Ачит-Нуур") == name_key("Achit nuur")
    assert name_key("Участок Ёлочка") == name_key("Yolochka")
    assert name_key("Проявления Далтын-Худаг (Солнечное)") == name_key("Daltyn Khudag")


def entry(name, latin, commodities=(), sheet="", page=1, **kw):
    return {"name_original": name, "name_latin": latin, "kind": "occurrence", "commodities": list(commodities),
            "minerals": [], "host_rocks": "", "alteration": "", "assays": [], "map_sheet": sheet, "map_number": "",
            "latitude": None, "longitude": None, "location_text": "", "report_section": "", "notes": "",
            "report": "4506", "pages": [page], **kw}


KNOWN = (
    Occurrence("NEA-1", "Namiryn gol", 49.35, 91.65, ("Cu",), "occurrence", "USGS", False),
    Occurrence("NEA-2", "Khargait 2", 49.45, 91.6, ("Cu",), "occurrence", "USGS", False),
    Occurrence("NEA-3", "Gozgor", 49.23, 91.95, ("Cu",), "occurrence", "USGS", False),
)


def test_locate_prefers_coordinates_then_name_then_sheet():
    feats, unlocated = locate([
        entry("Точка 1", "Point 1", ["Cu"], latitude=49.4, longitude=91.7),
        entry("Участок Намирин", "Namirin", page=2),
        entry("Участок Намирин", "Namirin", ["Cu"], page=5),  # same site on another page
        entry("Проявление 163", "163", ["Mo"], sheet="M-46-99-Б"),
        entry("Проявление Тасархай", "Tasarkhai"),
    ], KNOWN)
    by = {f["properties"]["name"]: f["properties"] for f in feats}
    assert by["Point 1"]["located_by"] == "printed coordinates"
    assert by["Namirin"]["usgs_match"]["id"] == "NEA-1"
    assert by["Namirin"]["commodities"] == ["Cu"] and "2, 5" in by["Namirin"]["source"]
    assert by["163"]["located_by"] == "centre of sheet M-46-99-Б"
    assert [u["name_latin"] for u in unlocated] == ["Tasarkhai"]


def test_locate_does_not_match_similar_name_with_other_commodity():
    feats, unlocated = locate([entry("Проявление Харгайту", "Khargaitu", ["coal"])], KNOWN)
    assert feats == [] and len(unlocated) == 1


def test_locate_flags_exact_name_with_conflicting_commodity():
    feats, _ = locate([entry("Проявление Гозгор", "Gozgor", ["Au"])], KNOWN)
    assert feats[0]["properties"]["usgs_match"]["commodity_conflict"] is True


def test_extract_page_sends_image_and_parses_schema(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    from archive.extract import MODEL, extract_page

    seen = {}
    answer = {"page_kind": "contents", "summary": "Contents.", "map_sheets": ["M-46-86-А"], "occurrences": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["beta"] = self.headers.get("anthropic-beta", "")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["content-length"])))
            body = json.dumps({
                "id": "msg_1", "type": "message", "role": "assistant", "model": MODEL,
                "content": [{"type": "text", "text": json.dumps(answer)}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = anthropic.Anthropic(api_key="test", base_url=f"http://127.0.0.1:{server.server_port}", max_retries=0)
        result = extract_page(client, b"\x89PNG fake", 6, "4506")
    finally:
        server.shutdown()

    assert result.map_sheets == ["M-46-86-А"]
    body = seen["body"]
    assert body["model"] == MODEL and body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen["beta"]
    assert body["messages"][0]["content"][0]["type"] == "image"
    assert body["output_config"]["format"]["type"] == "json_schema"
