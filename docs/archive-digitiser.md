# Soviet archive digitiser

Turns scanned Soviet survey reports into mapped mineral occurrences that the
prospectivity model can train on. Code: `backend/archive/`.

## Pipeline

1. **Extract** (`python -m archive.extract report.pdf --report 4506 --out out/archive/4506`):
   each page is rendered to an image and read by Claude (`claude-opus-5-5`), which
   returns every deposit, occurrence, mineralization point or anomaly on the page in a
   fixed schema (`archive/schema.py`): name as printed and transliterated, commodities,
   minerals, host rocks, alteration, assays, map sheet, map number, printed coordinates,
   and the section it sits under. Descriptions are translated to English, numbers are
   copied as printed, and nothing is filled in that the page does not state. Results
   are cached per page in `pages.jsonl`. Needs an Anthropic API key
   (`ANTHROPIC_API_KEY` or `ant auth login`).
2. **Locate** (`python -m archive.locate out/archive/4506/pages.jsonl --out out/archive/4506`):
   each entry is placed by printed coordinates, or by a name match with a site already
   in the database inside the report's area, or by the centre of its map sheet
   (Soviet nomenclature such as `M-46-86-Б`, `archive/sheets.py`), with a location
   uncertainty. The rest go to `unlocated.json`. Writes `occurrences.geojson` in the
   format the API reads.

## First sample: report 4506

`Historical Sample Data.pdf` (50 pages) is from *Geological structure and minerals of
the Kharkhiraa uplands in western Mongolia*, the 1991 report of the Kharkhiraa party
on 1:50,000 group geological mapping in 1988-90 (Sovgeo, contract 75-147/01200). It
covers 1:50,000 sheets M-46-86, 87, 88, 98, 99 and 100, that is about 90.5-92.0°E and
49.0-49.67°N, which is the heart of the pilot area and its copper cluster.

The sample holds the contents pages and the stratigraphy and tectonics chapters, not
the mineral descriptions. From the contents of chapter 8 it lists **28 named deposits
and occurrences**. Six match USGS sites by name (Namirin, Daltyn-Khudag, Otor-Ula,
Achit-Nuur, Yolochka, Gozgor), which confirms the report covers our training area.
22, among them Tasarkhai, occurrences 163 and 429, Razlomnoe, Khogshar-Bulak, Altan,
Taliin Sala, Shibein Gol, Zapredelnyi and Shar-Ukha, are new to us but need the
description pages or the map to be placed. One conflict is already visible: the report
files Gozgor under precious metals (gold), while USGS lists it as copper.

This first extraction was done in the project thread with the same schema, since the
cloud session has no API key; the outputs are in the project folder under
`critiore-mvp/archive/4506/`.

## What would unlock the most

The contents show that **volume II, book 1** holds a catalogue of deposits, occurrences
and mineralization points by commodity: copper alone runs over pages 14-62, gold 91-106,
tungsten 77-82 and molybdenum 75-77, followed by catalogues of heavy-mineral halos and of
lithochemical halos and dispersion streams. With the report's 1:50,000 geological and
mineral maps to place the numbered entries, that is likely hundreds of located copper
sites against the 8 the model trains on today.
