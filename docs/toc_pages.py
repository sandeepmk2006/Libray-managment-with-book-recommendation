"""Find the PDF page of every table-of-contents entry, for the static TOC.

Usage: python docs/toc_pages.py report.docx report.pdf pages.json
"""
import json
import re
import sys

import docx
import pymupdf
from docx.oxml.ns import qn

DOCX, PDF, OUT = sys.argv[1:4]
d = docx.Document(DOCX)
sdt = next(el for el in d.element.body.iterchildren() if el.tag == qn("w:sdt"))
labels = []
for p in sdt.iter(qn("w:p")):
    runs = p.findall(qn("w:r"))
    text = "".join(t.text or "" for r in runs for t in r.iter(qn("w:t")))
    label = re.sub(r"\d+$", "", text).strip()
    if label:
        labels.append(label)

pages = [re.sub(r"\s+", " ", pg.get_text()) for pg in pymupdf.open(PDF)]
norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
found, start = {}, 3          # skip cover, title and contents pages
chapter_page = start
for label in labels:
    m = re.match(r"Chapter (\d+): (.*)", label)
    if m:
        needle = f"chapter {m.group(1)} {m.group(2)}".lower()
    elif label in ("Abstract", "References", "PPT Handouts", "Microsoft Certificate", "Evaluation Sheet"):
        needle = label.lower()
    else:
        needle = label.lower()
    for i in range(chapter_page if not m else start, len(pages)):
        if needle in norm(pages[i]):
            found[label] = i + 1
            if m:
                chapter_page = i
            break
missing = [l for l in labels if l not in found]
json.dump(found, open(OUT, "w"), indent=1)
print(len(found), "entries located", "missing:", missing)
