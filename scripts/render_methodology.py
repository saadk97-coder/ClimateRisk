#!/usr/bin/env python3
"""
Render docs/TRANSITION_METHODOLOGY.md to a PDF via headless Chromium.

    pip install markdown playwright     # Chromium is pre-provisioned in the sandbox
    python scripts/render_methodology.py [output.pdf]
"""
import glob
import os
import sys

import markdown
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "TRANSITION_METHODOLOGY.md")

_CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Helvetica, Arial, sans-serif; color: #1c1c1c; line-height: 1.5; font-size: 10.5pt; }
h1 { font-size: 21pt; color: #a8480a; border-bottom: 3px solid #F4721A; padding-bottom: 6px; margin-top: 0; }
h2 { font-size: 15pt; border-left: 4px solid #F4721A; padding-left: 10px; margin-top: 26px; page-break-after: avoid; }
h3 { font-size: 12pt; color: #333; margin-top: 18px; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9pt; page-break-inside: avoid; }
th, td { border: 1px solid #d8d0c4; padding: 5px 8px; text-align: left; vertical-align: top; }
th { background: #f3ede4; }
code { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 8.6pt; background: #f4f1ea; padding: 1px 4px; border-radius: 3px; }
pre { background: #f7f4ee; border: 1px solid #e6ded0; border-radius: 6px; padding: 10px 12px; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.4pt; line-height: 1.35; }
hr { border: 0; border-top: 1px solid #e0d8c8; margin: 20px 0; }
a { color: #a8480a; } strong { color: #111; }
"""


def render(out_path: str) -> None:
    body = markdown.markdown(open(SRC, encoding="utf-8").read(),
                             extensions=["tables", "fenced_code", "toc"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{body}</body></html>"
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0]
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, **({"executable_path": exe} if exe else {}))
        pg = b.new_page()
        pg.set_content(html, wait_until="load")
        pg.pdf(path=out_path, format="A4", print_background=True,
               display_header_footer=True, header_template="<div></div>",
               footer_template="<div style='font-size:8px;color:#999;width:100%;text-align:center;'>"
                               "BSR Transition Risk — Methodology · page <span class='pageNumber'></span> "
                               "of <span class='totalPages'></span></div>")
        b.close()
    print("wrote", out_path)


if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "TRANSITION_METHODOLOGY.pdf"))
