"""Extract mineral occurrences from a scanned Soviet survey report with Claude.

    cd backend
    pip install -r requirements-archive.txt
    export ANTHROPIC_API_KEY=...            # or `ant auth login`
    python -m archive.extract "Historical Sample Data.pdf" --report 4506 --out out/archive/4506

Each page is rendered to an image and read by Claude, which returns the occurrences
on it in a fixed schema (archive/schema.py). Results are cached per page in
pages.jsonl, so a rerun only reads pages it has not seen. Then `archive.locate` turns
the entries into GeoJSON the API and the model can use.
"""

import argparse
import base64
import io
import json
from pathlib import Path

from .schema import PageExtraction

MODEL = "claude-opus-5-5"
DPI = 150

SYSTEM = """You digitise Soviet and Mongolian geological survey reports (1950s-1990s, mostly Russian,
typewritten, scanned) for a mineral exploration team. For each page image, record every mineral
deposit, occurrence, mineralization point, geochemical halo or stream anomaly that the page names,
with what the page says about it. Translate descriptions to English; keep names as printed and
also transliterate them. Copy numbers exactly as printed, including map sheets such as M-46-86-Б.
Only fill latitude/longitude when the page prints coordinates. Never invent values: leave a field
empty when the page does not state it. If the scan is too poor to read a value, leave it out and
say so in notes."""


def render_pages(pdf: Path, pages: list[int], dpi: int = DPI):
    """Yield (page_number, PNG bytes), page numbers 1-based."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    for n in pages:
        img = doc[n - 1].render(scale=dpi / 72).to_pil().convert("L")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        yield n, buf.getvalue()


def extract_page(client, png: bytes, page: int, report: str) -> PageExtraction:
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "high"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.standard_b64encode(png).decode()}},
                {"type": "text", "text": f"Report {report}, page {page} of the scan. Extract it."},
            ],
        }],
        output_format=PageExtraction,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"page {page}: no extraction (stop_reason={response.stop_reason})")
    return response.parsed_output


def parse_pages(spec: str, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--report", required=True, help="archive id of the report, e.g. 4506")
    ap.add_argument("--pages", default="", help="e.g. 1-8,40 (default: all)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    import anthropic
    import pypdfium2 as pdfium

    args.out.mkdir(parents=True, exist_ok=True)
    cache = args.out / "pages.jsonl"
    done = set()
    if cache.exists():
        done = {json.loads(line)["page"] for line in cache.read_text().splitlines() if line.strip()}

    pages = [p for p in parse_pages(args.pages, len(pdfium.PdfDocument(str(args.pdf)))) if p not in done]
    client = anthropic.Anthropic()
    with cache.open("a") as f:
        for n, png in render_pages(args.pdf, pages):
            try:
                result = extract_page(client, png, n, args.report)
            except (anthropic.APIStatusError, anthropic.APIConnectionError, RuntimeError) as e:
                print(f"page {n}: failed: {e}")
                continue
            f.write(json.dumps({"report": args.report, "page": n, **result.model_dump()}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"page {n}: {result.page_kind}, {len(result.occurrences)} occurrences")


if __name__ == "__main__":
    main()
