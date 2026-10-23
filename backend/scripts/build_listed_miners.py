"""Builds the listed-miners layer: mines and projects in Mongolia run by publicly traded companies.

The list is hand-curated from company releases, exchange filings and the Global Energy
Monitor coal tracker, checked October 2026. Each site keeps its sources so a reviewer can
trace every field. Edit SITES and rerun:

    python -m scripts.build_listed_miners

Writes data/listed_miners_mongolia.geojson.

Coordinates marked "approximate" were placed from a licence centre or a stated distance
and bearing (e.g. "21 km south-east of Boroo"), so treat them as within ~10 km.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "listed_miners_mongolia.geojson"
AS_OF = "2026-10"

GEM = "https://www.gem.wiki/"
MSE_LIST = "https://en.wikipedia.org/wiki/List_of_companies_listed_on_the_Mongolian_Stock_Exchange"
USGS_NEASIA = "https://pubs.usgs.gov/of/2003/of03-220/"

RIO = {"name": "Rio Tinto", "tickers": ["LSE: RIO", "ASX: RIO", "NYSE: RIO"]}
ENTREE = {"name": "Entrée Resources", "tickers": ["TSX: ETG", "OTCQB: ERLFF"]}
MMC = {"name": "Mongolian Mining Corporation", "tickers": ["HKEX: 975"]}
ERDENE = {"name": "Erdene Resource Development", "tickers": ["TSX: ERD", "MSE: ERDN", "OTCQX: ERDCF"]}
STEPPE = {"name": "Steppe Gold", "tickers": ["TSX: STGO", "OTCQX: STPGF"]}
SOUTHGOBI = {"name": "SouthGobi Resources", "tickers": ["HKEX: 1878", "TSXV: SGQ"]}
MEC = {"name": "Mongolia Energy Corporation", "tickers": ["HKEX: 276"]}
ZIJIN = {"name": "Zijin Mining", "tickers": ["HKEX: 2899", "SSE: 601899"]}
ASPIRE = {"name": "Aspire Mining", "tickers": ["ASX: AKM"]}
ELEF = {"name": "Silver Elephant Mining", "tickers": ["TSX: ELEF", "OTCQB: SILEF"]}

ERDENE_Q2 = ("https://www.cruxinvestor.com/posts/erdene-resource-development-reports-q2-2026-"
             "gold-production-and-advances-khundii-district-projects")
ERDENE_TR = "https://erdene.com/site/assets/files/3974/bayan_khundii_march_2017_technical_report.pdf"
MMC_Q2 = "https://www.mmc.mn/storage/announcements/July2026/eYBYJpa6W6Dgn3MC7Ucq.pdf"
STEPPE_BOROO = "https://www.newsfilecorp.com/release/218595"
SOUTHGOBI_Q2 = "https://www.newswire.com/news/southgobi-announces-second-quarter-2026-unaudited-financial-and-operating"
ENTREE_2026 = "https://pipelineroad.com/news/20260409-entr-e-resources-updates-on-joint-venture-licenses-and-explo"

# status: producing | development | exploration | standby | unverified
SITES = [
    dict(id="oyu-tolgoi", site="Oyu Tolgoi", lat=43.0028, lon=106.8583, precision="exact",
         province="Ömnögovi", commodities=["Cu", "Au", "Ag"], status="producing",
         companies=[{**RIO, "stake": "66%"}],
         ownership="Rio Tinto 66%, Erdenes Oyu Tolgoi (state) 34%",
         note="Open pit plus block-cave underground ramping up; 113.5 kt Cu in Q3 2026.",
         sources=["https://www.sec.gov/Archives/edgar/data/0000863064/000086306426000041/ex1prodresults.htm",
                  USGS_NEASIA]),
    dict(id="hugo-north-extension", site="Hugo North Extension (Shivee Tolgoi licence)",
         lat=43.08, lon=106.87, precision="approximate",
         province="Ömnögovi", commodities=["Cu", "Au"], status="development",
         companies=[{**ENTREE, "stake": "20%"}],
         ownership="Entrée/Oyu Tolgoi JV: Entrée 20%, Oyu Tolgoi LLC 80%",
         note="Northern extension of the Oyu Tolgoi underground ore body, mined through OT's Lift 1.",
         sources=[ENTREE_2026]),
    dict(id="heruga", site="Heruga (Javhlant licence)", lat=42.95, lon=106.80, precision="approximate",
         province="Ömnögovi", commodities=["Cu", "Au", "Mo"], status="exploration",
         companies=[{**ENTREE, "stake": "30%"}],
         ownership="Entrée/Oyu Tolgoi JV: Entrée 30%, Oyu Tolgoi LLC 70%",
         note="Deep porphyry deposit south of Oyu Tolgoi; resource stage.",
         sources=[ENTREE_2026]),
    dict(id="ukhaa-khudag", site="Ukhaa Khudag", lat=43.6668, lon=105.5181, precision="exact",
         province="Ömnögovi", commodities=["coking coal"], status="producing",
         companies=[{**MMC, "stake": "100%"}],
         ownership="Energy Resources LLC (100% MMC)",
         note="4.4 Mt raw coal mined in Q2 2026 (with Baruun Naran reported jointly).",
         sources=[MMC_Q2, GEM + "Ukhaa_Khudag_Coal_Mine"]),
    dict(id="baruun-naran", site="Baruun Naran", lat=43.5979, lon=105.2226, precision="exact",
         province="Ömnögovi", commodities=["coking coal"], status="producing",
         companies=[{**MMC, "stake": "controlled"}],
         ownership="Khangad Exploration LLC (MMC-controlled)",
         note="", sources=[MMC_Q2, GEM + "Baruun_Naran_Coal_Mine"]),
    dict(id="bayan-khundii", site="Bayan Khundii", lat=43.9488, lon=98.8000, precision="approximate",
         province="Bayankhongor", commodities=["Au", "Ag"], status="producing",
         companies=[{**ERDENE, "stake": "50%"}, {**MMC, "stake": "50%"}],
         ownership="Erdene Mongol LLC: Erdene 50%, MMC 50%",
         note="First gold Sept 2025; 11,709 oz Au sold in Q2 2026. Point is the Khundii licence centre.",
         sources=[ERDENE_Q2, MMC_Q2, ERDENE_TR]),
    dict(id="altan-nar", site="Altan Nar", lat=44.08, lon=98.70, precision="approximate",
         province="Bayankhongor", commodities=["Au", "Ag", "Pb", "Zn"], status="development",
         companies=[{**ERDENE, "stake": "100%"}],
         ownership="Erdene", note="About 16 km north-west of Bayan Khundii; resource revised Q2 2026.",
         sources=[ERDENE_Q2, ERDENE_TR]),
    dict(id="zuun-mod", site="Zuun Mod", lat=43.95, lon=99.30, precision="approximate",
         province="Bayankhongor", commodities=["Mo", "Cu"], status="development",
         companies=[{**ERDENE, "stake": "100%"}],
         ownership="Erdene", note="About 40 km east of Bayan Khundii; PEA due H2 2026.",
         sources=[ERDENE_Q2, ERDENE_TR]),
    dict(id="ato", site="ATO (Altan Tsagaan Ovoo)", lat=48.55, lon=112.72, precision="approximate",
         province="Dornod", commodities=["Au", "Ag", "Pb", "Zn"], status="producing",
         companies=[{**STEPPE, "stake": "100%"}],
         ownership="Steppe Gold 100%", note="38 km west of Tsagaan-Ovoo soum centre.",
         sources=[STEPPE_BOROO,
                  "https://www.mining-technology.com/projects/altan-tsagaan-ovoo-ato-gold-and-silver-project-dornod-mongolia/"]),
    dict(id="boroo", site="Boroo", lat=48.75, lon=106.15, precision="exact",
         province="Selenge", commodities=["Au"], status="producing",
         companies=[{**STEPPE, "stake": "100%"}],
         ownership="Boroo Gold LLC, acquired by Steppe Gold Aug 2024",
         note="Mill also treats Ulaanbulag ore.",
         sources=[STEPPE_BOROO, "https://miningdataonline.com/property/1030/Boroo-Mine.aspx", USGS_NEASIA]),
    dict(id="ulaanbulag", site="Ulaanbulag", lat=48.62, lon=106.35, precision="approximate",
         province="Selenge", commodities=["Au"], status="producing",
         companies=[{**STEPPE, "stake": "100%"}],
         ownership="Boroo Gold LLC (Steppe Gold)", note="Satellite pit about 21 km south-east of Boroo.",
         sources=[STEPPE_BOROO, "https://miningdataonline.com/property/1030/Boroo-Mine.aspx"]),
    dict(id="ovoot-tolgoi", site="Ovoot Tolgoi", lat=43.0022, lon=101.2606, precision="exact",
         province="Ömnögovi", commodities=["coking coal", "thermal coal"], status="producing",
         companies=[{**SOUTHGOBI, "stake": "100%"}],
         ownership="SouthGobi Sands LLC (100% SouthGobi)",
         note="3.5 Mt sold in Q2 2026; designated a deposit of strategic importance.",
         sources=[SOUTHGOBI_Q2, GEM + "Ovoot_Tolgoi_Coal_Mine"]),
    dict(id="soumber", site="Soumber", lat=43.00, lon=101.51, precision="approximate",
         province="Ömnögovi", commodities=["coking coal"], status="development",
         companies=[{**SOUTHGOBI, "stake": "100%"}],
         ownership="SouthGobi", note="About 20 km east of Ovoot Tolgoi; one licence still in a protected area.",
         sources=[SOUTHGOBI_Q2]),
    dict(id="khushuut", site="Khushuut", lat=46.8072, lon=93.3096, precision="exact",
         province="Khovd", commodities=["coking coal"], status="producing",
         companies=[{**MEC, "stake": "100%"}],
         ownership="MoEnCo (100% Mongolia Energy Corp)", note="Relocating site facilities by 2027.",
         sources=["https://www.webull.com.au/news-detail/15439987216917504", GEM + "Khushuut_Coal_Mine"]),
    dict(id="kharmagtai", site="Kharmagtai", lat=44.0319, lon=106.1444, precision="exact",
         province="Ömnögovi", commodities=["Cu", "Au"], status="development",
         companies=[{**ZIJIN, "stake": "38.25% effective"}],
         ownership="Khuiten Metals 76.5%, itself 50/50 Zijin and Bastion Mining (private, Boroo-led)",
         note="Zijin operates since Sept 2024; PFS done. Xanadu Mines, the former ASX/TSX partner, "
              "was taken private by Bastion in 2025.",
         sources=["https://www.businessnews.com.au/article/Xanadu-hands-ball-to-Zijin-for-Mongolian-copper-gold-goal",
                  "https://www.tipranks.com/news/company-announcements/xanadu-mines-ltd-to-be-delisted-following-acquisition",
                  USGS_NEASIA]),
    dict(id="ovoot-coking", site="Ovoot coking coal project", lat=49.3641, lon=97.4965, precision="approximate",
         province="Khövsgöl", commodities=["coking coal"], status="development",
         companies=[{**ASPIRE, "stake": "100%"}],
         ownership="Aspire Mining 100%", note="Permitted; construction not started as of early 2026.",
         sources=[GEM + "Ovoot_Coking_Project"]),
    dict(id="ulaan-ovoo", site="Ulaan Ovoo", lat=50.3178, lon=104.9736, precision="exact",
         province="Selenge", commodities=["thermal coal"], status="standby",
         companies=[{**ELEF, "stake": "100%"}],
         ownership="Silver Elephant 100%",
         note="Leased July 2026 to a Mongolian operator who will mine it for a per-tonne royalty.",
         sources=["https://www.newsfilecorp.com/release/304044", GEM + "Ulaan_Ovoo_Coal_Mine"]),
    # Mongolian Stock Exchange coal producers. Most are state or province majority-owned.
    dict(id="baganuur", site="Baganuur", lat=47.7506, lon=108.3249, precision="exact",
         province="Ulaanbaatar (Baganuur)", commodities=["thermal coal"], status="producing",
         companies=[{"name": "Baganuur JSC", "tickers": ["MSE: BAN"], "stake": "100%"}],
         ownership="Baganuur JSC (state majority)", note="About 5 Mt in 2024; supplies Ulaanbaatar power plants.",
         sources=[GEM + "Baganuur_Coal_Mine", MSE_LIST]),
    dict(id="shivee-ovoo", site="Shivee Ovoo", lat=46.2240, lon=108.5307, precision="approximate",
         province="Govisümber", commodities=["thermal coal"], status="producing",
         companies=[{"name": "Shivee Ovoo JSC", "tickers": ["MSE: SHV"], "stake": "100%"}],
         ownership="Shivee Ovoo JSC (state majority)", note="GEM gives two locations; this is the Details one.",
         sources=[GEM + "Shivee-Ovoo_mine", MSE_LIST]),
    dict(id="tavan-tolgoi-small", site="Tavan Tolgoi (provincial licence)", lat=43.6517, lon=105.4417,
         precision="approximate", province="Ömnögovi", commodities=["coking coal"], status="producing",
         companies=[{"name": "Tavan Tolgoi JSC", "tickers": ["MSE: TTL"], "stake": "100%"}],
         ownership="Ömnögovi province majority",
         note="Small licence beside the state Erdenes Tavan Tolgoi field (not listed yet); 4.3 Mt in 2024.",
         sources=[GEM + "Tavan_Tolgoi_(Small)_Coal_Mine", MSE_LIST]),
    dict(id="sharyn-gol", site="Sharyn Gol", lat=49.2282, lon=106.4220, precision="exact",
         province="Darkhan-Uul", commodities=["thermal coal"], status="unverified",
         companies=[{"name": "Sharyn Gol JSC", "tickers": ["MSE: SHG"], "stake": "100%"}],
         ownership="Sharyn Gol JSC", note="Long-running mine; current output not confirmed.",
         sources=["https://en.wikipedia.org/wiki/Sharyn_Gol_Coal_Mine", MSE_LIST]),
    dict(id="aduunchuluun", site="Aduunchuluun", lat=48.1272, lon=114.5378, precision="exact",
         province="Dornod", commodities=["thermal coal"], status="producing",
         companies=[{"name": "Aduunchuluun JSC", "tickers": ["MSE: ADL"], "stake": "100%"}],
         ownership="Aduunchuluun JSC (GEM also names MAK as owner)", note="Supplies Choibalsan.",
         sources=[GEM + "Aduunchuluun_Coal_Mine", MSE_LIST]),
    dict(id="mogoin-gol", site="Mogoin Gol", lat=49.3584, lon=97.8296, precision="exact",
         province="Khövsgöl", commodities=["thermal coal"], status="producing",
         companies=[{"name": "Mogoin Gol JSC", "tickers": ["MSE: BDL"], "stake": "100%"}],
         ownership="Mogoin Gol JSC", note="", sources=[GEM + "Mogoin_Gol_Coal_Mine", MSE_LIST]),
    dict(id="bayanteeg", site="Bayanteeg", lat=45.6973, lon=101.5600, precision="exact",
         province="Övörkhangai", commodities=["thermal coal"], status="unverified",
         companies=[{"name": "Bayanteeg JSC", "tickers": ["MSE: BTG"], "stake": "100%"}],
         ownership="Bayanteeg JSC", note="Small underground mine; current output not confirmed.",
         sources=["https://en.wikipedia.org/wiki/Bayanteeg_Coal_Mine", MSE_LIST]),
]


def feature(s: dict) -> dict:
    props = {k: v for k, v in s.items() if k not in ("lat", "lon")}
    props["as_of"] = AS_OF
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
            "properties": props}


def main():
    fc = {"type": "FeatureCollection", "features": [feature(s) for s in SITES]}
    OUT.write_text(json.dumps(fc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(SITES)} sites to {OUT}")


if __name__ == "__main__":
    main()
