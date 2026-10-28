"""
Channel logos for e-paper: downloaded once from the feed's icon URL, trimmed, shrunk and turned to grayscale.

The cache directory keeps the processed logos between runs, with manifest.json mapping each channel to the URL its
logo came from: a logo is fetched again only when that URL changes. Needs Pillow.
"""
import hashlib
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

# Twice the size the views draw at most, for sharp edges on TRMNL X.
BOX = (200, 80)
# Darkens colors (orange Arte, red M6) so they don't fade to light gray on the screen.
GAMMA = 2.2
# Logos lighter than this on average (white on transparent) are inverted, or they would vanish on white.
LIGHT = 200


def process(data):
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    alpha = im.getchannel("A")
    if alpha.getextrema()[0] == 255:
        # Opaque: trim the white margins, and make white transparent.
        gray = im.convert("L")
        bbox = ImageOps.invert(gray).point(lambda v: 255 if v > 16 else 0).getbbox()
        alpha = ImageOps.invert(gray).point(lambda v: 0 if v < 16 else 255)
        im.putalpha(alpha)
    else:
        bbox = alpha.point(lambda v: 255 if v > 16 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    im.thumbnail(BOX, Image.LANCZOS)

    gray = im.convert("L")
    alpha = im.getchannel("A")
    opaque = [g for g, a in zip(gray.getdata(), alpha.getdata()) if a > 128]
    if opaque and sum(opaque) / len(opaque) > LIGHT:
        gray = ImageOps.invert(gray)
    gray = gray.point(lambda v: int(255 * (v / 255) ** GAMMA))
    gray.putalpha(alpha)
    out = io.BytesIO()
    gray.save(out, "PNG", optimize=True)
    return out.getvalue()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (trmnl-tv-schedule)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def update(icons, cache_dir):
    """Brings the cache up to date with {channel id: icon URL}; returns the ids that have a logo."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    manifest_path = cache / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    todo = {cid: url for cid, url in icons.items()
            if url and (manifest.get(cid) != url or not (cache / f"{cid}.png").exists())}

    def one(item):
        cid, url = item
        try:
            (cache / f"{cid}.png").write_bytes(process(fetch(url)))
            return cid, url
        except Exception as e:  # a dead link or an odd image: the channel shows its name instead
            print(f"logo {cid}: {e}")
            return cid, None

    with ThreadPoolExecutor(max_workers=16) as pool:
        for cid, url in pool.map(one, todo.items()):
            if url:
                manifest[cid] = url
            else:
                manifest.pop(cid, None)
                (cache / f"{cid}.png").unlink(missing_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=0, sort_keys=True))
    print(f"logos: {len(todo)} fetched, {len(manifest)} in cache")
    return {cid for cid in icons if cid in manifest and (cache / f"{cid}.png").exists()}


def unique(ids, cache_dir):
    """Leaves out logos shared by several channels (Eurosport 360, Canal+ Live...): their names tell them apart."""
    by_hash = {}
    for cid in ids:
        by_hash.setdefault(hashlib.sha1((Path(cache_dir) / f"{cid}.png").read_bytes()).digest(), []).append(cid)
    return {cid for group in by_hash.values() if len(group) == 1 for cid in group}
