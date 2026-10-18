"""Build licensed, renamed WOFF2 subsets from the supplied font masters."""

import hashlib
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

SITE = Path(__file__).resolve().parents[1]
BASE = set(range(0x20, 0x300)) | set(range(0x1E00, 0x1F00)) | set(range(0x2000, 0x2070))
corpus = set()
for root in ("guides", "agents", "commands", "configs"):
    for source in (SITE.parent / root).rglob("*.md"):
        corpus.update(map(ord, source.read_text()))

records = []
for family, alias, filename in (
    ("SourceSerif4", "crefft Reading", "reading"),
    ("SourceCodePro", "crefft Mono", "mono"),
):
    for style, weight in (("Regular", 400), ("Semibold", 600)):
        source = SITE / "assets/fonts" / f"{family}-{style}.ttf"
        font = TTFont(source, recalcTimestamp=False)
        options = subset.Options()
        options.flavor = "woff2"
        options.name_IDs = ["*"]
        options.name_legacy = True
        options.name_languages = ["*"]
        options.notdef_glyph = True
        options.notdef_outline = True
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=(BASE | corpus) & set(font.getBestCmap()))
        subsetter.subset(font)
        # Subsetting is a modification; do not reuse Adobe's reserved font name.
        for record in font["name"].names:
            if record.nameID in (1, 3, 4, 6, 16):
                value = alias if record.nameID in (1, 16) else f"{alias} {style}"
                if record.nameID == 6:
                    value = value.replace(" ", "-")
                record.string = value.encode(record.getEncoding())
        font.flavor = "woff2"
        target = SITE / "public/fonts" / f"{filename}-{weight}.woff2"
        font.save(target)
        records.append({
            "source": source.name,
            "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "file": target.name,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size,
            "family": alias,
        })
(SITE / "public/fonts/manifest.json").write_text(json.dumps(records, indent=2) + "\n")
print(f"Built {len(records)} WOFF2 subsets: {sum(row['bytes'] for row in records)} bytes")
