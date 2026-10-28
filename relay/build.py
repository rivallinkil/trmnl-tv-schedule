"""
Splits the XMLTV guide of the channels available in France (xmltvfr.fr, ~400 channels, 9 MB gzipped) into one
small JSON file per channel, which TRMNL polls (it rejects responses over 100 KB).

Runs on a schedule in GitHub Actions (.github/workflows/relay.yml), which publishes the output on GitHub Pages:
  channels.json   [{"id": "TF1.fr", "name": "TF1"}, ...]    TNT channels in channel-number order, then the rest by name
  c/<id>.json     {"id", "name", "logo", "generated", "programmes": [[start, stop, title, category], ...]}
                  epoch seconds; "logo" is the URL of logos/<id>.png, or null
  logos/<id>.png  the channel's logo, ready for e-paper (relay/logos.py)

Only programmes still running or starting in the next WINDOW_HOURS are kept.

  python3 relay/build.py public --logos .cache/logos --base-url https://rivallinkil.github.io/trmnl-tv-schedule
  python3 relay/build.py out --input xmltv_fr.xml.gz --now 1793142000 --only TF1.fr,Arte.fr   # test fixtures
"""
import argparse
import gzip
import io
import json
import shutil
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

SOURCE = "https://xmltvfr.fr/xmltv/xmltv_fr.xml.gz"
WINDOW_HOURS = 30
# TRMNL rejects polled responses over 100 KB; one channel is a few KB.
MAX_BYTES = 90_000
# The French TNT, in channel-number order: listed first in the settings.
TNT = [
    "TF1.fr", "France2.fr", "France3.fr", "CanalPlus.fr", "France5.fr", "M6.fr", "Arte.fr", "W9.fr", "TMC.fr",
    "NT1.fr", "LaChaineParlementaire.fr", "France4.fr", "BFMTV.fr", "CNews.fr", "CStar.fr", "Gulli.fr", "T18.fr",
    "NOVO19.fr", "TF1SeriesFilms.fr", "LEquipe21.fr", "6ter.fr", "Numero23.fr", "RMCDecouverte.fr", "Cherie25.fr",
    "LCI.fr", "FranceInfo.fr", "ParisPremiere.fr", "CanalPlusSport.fr", "CanalPlusCinema.fr", "PlanetePlus.fr",
]
# Feed names that read badly on the screen.
NAMES = {
    "LEquipe21.fr": "L'Équipe",
    "FranceInfo.fr": "franceinfo",
    "TF1SeriesFilms.fr": "TF1 Séries Films",
    "Numero23.fr": "RMC Story",
    "Cherie25.fr": "RMC Life",
    "LaChaineParlementaire.fr": "LCP",
    "CanalPlusCinema.fr": "Canal+ Cinéma",
    "PlanetePlus.fr": "Planète+",
    "AdultSwim.fr": "Adult Swim",
    "BipTV.fr": "BIP TV",
    "DisneyChannelPlus1.fr": "Disney Channel +1",
    "FightSports.fr": "Fight Sports",
    "FuelTV.fr": "Fuel TV",
    "InfosportPlus.fr": "Infosport+",
    "LaChaineMeteo.fr": "La Chaîne Météo",
    "MaisonEtTravaux.fr": "Maison & Travaux",
    "NatGeoWild.fr": "Nat Geo Wild",
    "NickelodeonPlus1.fr": "Nickelodeon +1",
    "PlayboyTV.fr": "Playboy TV",
    "StingrayClassica.fr": "Stingray Classica",
    "StingrayDjazz.fr": "Stingray Djazz",
    "StingrayFestival.fr": "Stingray Festival",
    "StingrayiConcerts.fr": "Stingray iConcerts",
}


def channel_name(cid, display_name):
    if cid in NAMES:
        return NAMES[cid]
    name = (display_name or cid).strip()
    # Some channels have their id as name: "FooTV.fr" -> "FooTV".
    return name.rsplit(".", 1)[0] if name == cid else name


def open_feed(path):
    if path:
        return gzip.open(path) if path.endswith(".gz") else open(path, "rb")
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "trmnl-tv-schedule"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    return gzip.GzipFile(fileobj=io.BytesIO(data))


def epoch(stamp):
    # "20261028211000 +0100"
    return int(datetime.strptime(stamp, "%Y%m%d%H%M%S %z").timestamp())


def build(feed, now, hours):
    """{id: name}, {id: icon URL} and {id: [programme, ...]}, streaming through the feed (73 MB unpacked)."""
    end = now + hours * 3600
    names, icons, programmes = {}, {}, {}
    for _, el in ET.iterparse(feed):
        if el.tag == "channel":
            cid = el.get("id")
            names[cid] = channel_name(cid, el.findtext("display-name"))
            icon = el.find("icon")
            icons[cid] = icon.get("src") if icon is not None else None
            programmes.setdefault(cid, [])
            el.clear()
        elif el.tag == "programme":
            start, stop = epoch(el.get("start")), epoch(el.get("stop"))
            if stop > now and start < end:
                programmes.setdefault(el.get("channel"), []).append([
                    start, stop, (el.findtext("title") or "").strip(), (el.findtext("category") or "").strip()])
            el.clear()
    for rows in programmes.values():
        rows.sort()
    return names, icons, programmes


def ordered(names):
    tnt = [c for c in TNT if c in names]
    rest = sorted((c for c in names if c not in TNT), key=lambda c: names[c].casefold())
    return tnt + rest


def dump(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", help="directory to write channels.json and c/ into")
    parser.add_argument("--input", help="a local XMLTV file (.xml or .xml.gz) instead of downloading it")
    parser.add_argument("--now", type=int, help="epoch seconds the window starts at (default: now)")
    parser.add_argument("--hours", type=int, default=WINDOW_HOURS)
    parser.add_argument("--only", help="comma-separated channel ids to write (test fixtures)")
    parser.add_argument("--logos", metavar="CACHE_DIR", help="fetch the logos, kept in CACHE_DIR between runs")
    parser.add_argument("--base-url", help="where the output is published, for the logo URLs")
    args = parser.parse_args()

    now = args.now or int(time.time())
    with open_feed(args.input) as feed:
        names, icons, programmes = build(feed, now, args.hours)
    total = sum(len(r) for r in programmes.values())
    if total == 0:
        sys.exit("no programmes in the window: is the feed outdated?")

    out = Path(args.output)
    shutil.rmtree(out / "c", ignore_errors=True)
    (out / "c").mkdir(parents=True)
    ids = ordered(names)
    if args.only:
        ids = [c for c in ids if c in args.only.split(",")]

    with_logo = set()
    shutil.rmtree(out / "logos", ignore_errors=True)
    if args.logos:
        import logos  # Pillow, only needed here

        with_logo = logos.unique(logos.update({c: icons.get(c) for c in ids}, args.logos), args.logos)
        (out / "logos").mkdir()
        for cid in with_logo:
            shutil.copy(Path(args.logos) / f"{cid}.png", out / "logos" / f"{cid}.png")
    base_url = (args.base_url or "").rstrip("/")

    for cid in ids:
        logo = f"{base_url}/logos/{cid}.png" if cid in with_logo else None
        data = dump({"id": cid, "name": names[cid], "logo": logo, "generated": now,
                     "programmes": programmes.get(cid, [])})
        if len(data) > MAX_BYTES:
            sys.exit(f"{cid}: {len(data)} bytes, over the {MAX_BYTES} limit")
        (out / "c" / f"{cid}.json").write_bytes(data)
    (out / "channels.json").write_bytes(dump([{"id": c, "name": names[c]} for c in ids]))
    print(f"{out}: {len(ids)} channels, {sum(len(programmes.get(c, [])) for c in ids)} programmes, {args.hours} h window")


if __name__ == "__main__":
    main()
