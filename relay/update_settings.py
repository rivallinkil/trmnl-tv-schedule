"""
Rewrites the options of the "channels" field in src/settings.yml from the relay's channels.json, so the list of
channels to pick from follows the feed. Run it after relay/build.py, then review the diff:

  python3 relay/build.py public && python3 relay/update_settings.py public/channels.json
"""
import json
import re
import sys
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent.parent / "src" / "settings.yml"


def quote(text):
    return "'" + text.replace("'", "''") + "'"


def main():
    channels = json.loads(Path(sys.argv[1]).read_text())
    options = "".join(f"  - {quote(c['name'])}: {c['id']}\n" for c in channels)
    text = SETTINGS.read_text()
    # The options list of the channels field: from its "options:" line up to the next field.
    pattern = re.compile(r"(- keyname: channels\n(?:  .*\n)*?  options:\n)(?:  - .*\n)*")
    if not pattern.search(text):
        sys.exit(f"no options list for the channels field in {SETTINGS}")
    SETTINGS.write_text(pattern.sub(lambda m: m.group(1) + options, text, count=1))
    print(f"{SETTINGS}: {len(channels)} channels")


if __name__ == "__main__":
    main()
