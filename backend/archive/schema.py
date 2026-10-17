"""What the LLM extracts from each scanned page. Kept close to how Soviet catalogues
record occurrences, so nothing is guessed at extraction time; locating happens later."""

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["deposit", "occurrence", "mineralization_point", "geochemical_halo", "stream_anomaly",
               "heavy_mineral_halo", "other"]


class Assay(BaseModel):
    element: str = Field(description="Chemical symbol, e.g. Cu, Mo, W, Au, Ag, Sn")
    value: float
    unit: str = Field(description="As written: %, g/t, ppm, %% etc.")
    context: str = Field(description="Sample or interval the value refers to, as written, translated to English")


class Occurrence(BaseModel):
    name_original: str = Field(description="Name exactly as printed (Cyrillic), or a number such as '163'")
    name_latin: str = Field(description="Name transliterated to Latin script, e.g. 'Namirin', 'Otor-Ula'")
    kind: Kind
    commodities: list[str] = Field(description="Chemical symbols of the main commodities, most important first")
    minerals: list[str] = Field(description="Ore and alteration minerals named, in English")
    host_rocks: str = Field(description="Host rocks and intrusions, in English; empty if not stated")
    alteration: str = Field(description="Alteration described (e.g. phyllic, skarn, greisen), in English; empty if none")
    assays: list[Assay]
    map_sheet: str = Field(description="Map sheet nomenclature as printed, e.g. 'M-46-86-Б'; empty if none")
    map_number: str = Field(description="Number of the object on the report's map, as printed; empty if none")
    latitude: float | None = Field(description="Decimal degrees north, only if coordinates are printed")
    longitude: float | None = Field(description="Decimal degrees east, only if coordinates are printed")
    location_text: str = Field(description="Location description, translated to English")
    report_section: str = Field(description="Section heading the entry sits under, translated, e.g. 'Non-ferrous metals'")
    notes: str = Field(description="Anything else relevant: size, reserves, recommended work, in English")


class PageExtraction(BaseModel):
    page_kind: Literal["title", "contents", "catalogue", "description", "table", "map", "figure", "other"]
    summary: str = Field(description="One sentence on what the page holds, in English")
    map_sheets: list[str] = Field(description="All map sheet names printed on the page")
    occurrences: list[Occurrence] = Field(description="Every mineral deposit, occurrence, point or anomaly "
                                          "named on the page, including entries in a table of contents")
