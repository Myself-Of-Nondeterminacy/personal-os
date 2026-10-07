#!/usr/bin/env python3
"""Extract basic metadata and TOC labels from EPUB files.

Usage: python scripts/epub_metadata.py <book.epub> [more.epub ...]
Prints metadata only; does not dump book text.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
}


def text_of(el: ET.Element | None) -> str:
    return "" if el is None else "".join(el.itertext())


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normpath(*parts: str) -> str:
    return "/".join(str(p).replace("\\", "/").strip("/") for p in parts if str(p) not in ("", "."))


def read_epub(path: Path) -> None:
    print(f"\n=== {path.name}")
    with ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find("container:rootfiles/container:rootfile", NS).attrib["full-path"]
        opf = ET.fromstring(z.read(rootfile))
        meta = opf.find("opf:metadata", NS)
        for tag in ["title", "creator", "language", "publisher", "date", "identifier", "description", "subject"]:
            vals = [clean(text_of(e)) for e in meta.findall(f"dc:{tag}", NS) if clean(text_of(e))]
            if vals:
                print(f"{tag}: {' | '.join(vals)[:800]}")

        manifest = {
            item.attrib.get("id"): (item.attrib.get("href"), item.attrib.get("media-type"), item.attrib.get("properties"))
            for item in opf.findall("opf:manifest/opf:item", NS)
        }
        spine = [ref.attrib.get("idref") for ref in opf.findall("opf:spine/opf:itemref", NS)]
        print(f"spine items: {len(spine)}")

        base = str(Path(rootfile).parent).replace("\\", "/")
        def resolve(href: str | None) -> str | None:
            return None if not href else normpath(base, href)

        toc: list[str] = []
        nav_id = next((i for i, (_, _, props) in manifest.items() if props and "nav" in props), None)
        if nav_id:
            href, _, _ = manifest[nav_id]
            nav = ET.fromstring(z.read(resolve(href)))
            toc = [clean(text_of(a)) for a in nav.findall('.//xhtml:nav[@epub:type="toc"]//xhtml:a', NS)]
            toc = [t for t in toc if t]
        if not toc:
            ncx_id = next((i for i, (_, mt, _) in manifest.items() if mt == "application/x-dtbncx+xml"), None)
            if ncx_id:
                href, _, _ = manifest[ncx_id]
                ncx = ET.fromstring(z.read(resolve(href)))
                for np in ncx.findall(".//ncx:navPoint", NS):
                    label = clean(text_of(np.find("ncx:navLabel/ncx:text", NS)))
                    if label:
                        toc.append(label)
        print(f"toc entries: {len(toc)}")
        for item in toc[:120]:
            print(f" - {item}")
        if len(toc) > 120:
            print(f" ... {len(toc) - 120} more")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    for arg in argv[1:]:
        read_epub(Path(arg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
