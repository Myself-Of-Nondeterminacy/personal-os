#!/usr/bin/env python3
"""Import an EPUB into an Obsidian vault as local full-text markdown chapters.

Writes only to the target vault folder. Prints a JSON summary, never book text.

Usage:
  python scripts/import_epub_fulltext_to_obsidian.py <book.epub> <vault_dir> <slug>
"""
from __future__ import annotations

import html
import json
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

BLOCK_TAGS = (
    "p", "div", "section", "article", "blockquote", "br", "li", "tr",
    "h1", "h2", "h3", "h4", "h5", "h6", "title", "td", "th",
)


def text_of(el: ET.Element | None) -> str:
    return "" if el is None else "".join(el.itertext())


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normpath(*parts: str) -> str:
    return "/".join(str(p).replace("\\", "/").strip("/") for p in parts if str(p) not in ("", "."))


def safe_name(s: str, fallback: str) -> str:
    s = clean(s) or fallback
    s = re.sub(r"[\\/:*?\"<>|]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:90] or fallback


def xhtml_to_markdown(data: bytes) -> str:
    s = data.decode("utf-8", "ignore")
    s = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", s, flags=re.I)
    # Preserve rough block structure before stripping tags.
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|section|article|blockquote|li|tr|h[1-6]|title)>", "\n\n", s, flags=re.I)
    s = re.sub(r"<(h[1-6])[^>]*>", "\n\n## ", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "\n- ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def read_epub(path: Path) -> dict:
    with ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find("container:rootfiles/container:rootfile", NS).attrib["full-path"]
        opf = ET.fromstring(z.read(rootfile))
        meta = opf.find("opf:metadata", NS)
        title = clean(text_of(meta.find("dc:title", NS))) or path.stem
        author = clean(text_of(meta.find("dc:creator", NS)))
        manifest = {
            item.attrib.get("id"): (item.attrib.get("href"), item.attrib.get("media-type"), item.attrib.get("properties"))
            for item in opf.findall("opf:manifest/opf:item", NS)
        }
        spine = [ref.attrib.get("idref") for ref in opf.findall("opf:spine/opf:itemref", NS)]
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

        docs: list[dict] = []
        for idx, idref in enumerate(spine, start=1):
            item = manifest.get(idref)
            if not item:
                continue
            href, media_type, _ = item
            fname = resolve(href)
            if not fname or not fname.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            try:
                data = z.read(fname)
            except KeyError:
                continue
            body = xhtml_to_markdown(data)
            if not body:
                continue
            if len(toc) == len(docs) + 1 and idx == 1:
                label = toc[0]
            elif len(toc) == len(spine) and idx <= len(toc):
                label = toc[idx - 1]
            elif len(toc) == len(spine) - 1 and idx == 1:
                label = "封面"
            elif len(toc) == len(spine) - 1 and idx > 1 and idx - 2 < len(toc):
                label = toc[idx - 2]
            elif idx - 1 < len(toc):
                label = toc[idx - 1]
            else:
                first = next((ln.strip("# ") for ln in body.splitlines() if ln.strip()), f"Section {idx:02d}")
                label = first
            docs.append({"index": idx, "label": clean(label), "body": body})
        return {"title": title, "author": author, "docs": docs, "source": str(path)}


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__.strip())
        return 2
    epub = Path(argv[1])
    vault = Path(argv[2])
    slug = safe_name(argv[3], "book")
    info = read_epub(epub)
    outdir = vault / "30_Resources" / "Books" / "_fulltext" / slug
    outdir.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    links: list[tuple[str, str]] = []
    for doc in info["docs"]:
        idx = doc["index"]
        label = doc["label"]
        fname = f"{idx:02d}_{safe_name(label, f'section-{idx:02d}')}.md"
        fpath = outdir / fname
        content = (
            "---\n"
            f"book: {info['title']}\n"
            f"chapter: {label}\n"
            f"source_epub: {info['source']}\n"
            "local_fulltext: true\n"
            "generated_by: personal-os/scripts/import_epub_fulltext_to_obsidian.py\n"
            "---\n\n"
            f"# {label}\n\n"
            f"{doc['body']}\n"
        )
        data = content.encode("utf-8")
        fpath.write_bytes(data)
        total_bytes += len(data)
        links.append((label, fname))

    index_lines = [
        "---",
        f"book: {info['title']}",
        "local_fulltext_index: true",
        "---",
        "",
        f"# {info['title']}｜全文索引",
        "",
        f"作者：{info['author']}" if info["author"] else "",
        f"章节数：{len(links)}",
        "",
        "## 章节",
        "",
    ]
    for label, fname in links:
        stem = fname[:-3]
        index_lines.append(f"- [[{stem}|{label}]]")
    index = "\n".join(x for x in index_lines if x is not None) + "\n"
    (outdir / "index.md").write_text(index, encoding="utf-8")
    total_bytes += len(index.encode("utf-8"))

    print(json.dumps({
        "book": info["title"],
        "author": info["author"],
        "chapters_written": len(links),
        "outdir": str(outdir),
        "bytes": total_bytes,
        "mb": round(total_bytes / 1024 / 1024, 3),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
