"""Convert an HTML slide deck to an editable PPTX via html-to-pptx.

Wraps ``html_to_pptx.convert`` with the two fixes this project always needs:

1. Zoom injection — decks authored on a fixed stage (e.g. 1280×720) scaled by
   CSS ``transform: scale()`` measure at layout space once the extractor clears
   ancestor transforms, so content lands on only 2/3 of the fixed 1920×1080
   canvas. ``zoom`` is not a transform and survives measurement, so we inject
   ``zoom = 1920 / stage-width`` on the detected slide element.
2. External font stripping — remote font <link>s (Google Fonts etc.) make the
   converter's networkidle wait hang; they are removed before conversion.

Usage:
    python html2pptx.py input.html output.pptx [--zoom auto|1.5] [--no-strip-fonts]
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import tempfile
from pathlib import Path

CANVAS_WIDTH = 1920  # html-to-pptx fixes the PPTX canvas at 1920×1080 CSS px

# Remote font/stylesheet hosts known to hang the networkidle wait.
REMOTE_FONT_RE = re.compile(
    r"<link\b[^>]*rel=[\"'](?:stylesheet|preconnect)[\"'][^>]*>"
    r"|<link\b[^>]*href=[\"']https?://[^\"']*(?:fonts\.|font|cdn)[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)


def detect_stage(html_path: Path) -> tuple[str, float] | None:
    """Find the slide stage selector and its layout-space width in Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('playwright is missing: pip install playwright && python -m playwright install chromium')
        return None

    probe = r"""
    () => {
      const candidates = [
        ...document.querySelectorAll('section.slide, .slide, .slide-container, .stage, .deck, section'),
      ];
      let best = null;
      for (const el of candidates) {
        const rect = el.getBoundingClientRect();
        const w = el.offsetWidth;
        if (w < 800 || w > 3000) continue;
        if (!best || w > best.w) best = { el, w, x: rect.x, y: rect.y };
      }
      if (!best) return null;
      const tag = best.el.tagName.toLowerCase();
      const cls = (best.el.classList.length ? '.' + [...best.el.classList].join('.') : '');
      return { selector: tag + cls, width: best.w };
    }
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.goto(html_path.resolve().as_uri(), wait_until='load', timeout=30000)
        result = page.evaluate(probe)
        browser.close()
    return (result['selector'], float(result['width'])) if result else None


def strip_remote_fonts(html: str) -> str:
    """Remove remote stylesheet/font <link>s that hang the converter's load wait."""
    cleaned, count = REMOTE_FONT_RE.subn('', html)
    if count:
        print(f'stripped {count} remote font/stylesheet <link>(s)')
    return cleaned


def inject_zoom(html: str, selector: str, zoom: float) -> str:
    """Append a zoom override for the stage element before </head>."""
    style = (
        f'<style id="html2pptx-zoom-inject">\n'
        f'  {selector} {{ zoom: {zoom:.4g} !important; }}\n'
        f'</style>\n</head>'
    )
    if '</head>' in html:
        return html.replace('</head>', style, 1)
    return f'{style}\n{html}'


async def convert(input_html: Path, output_pptx: Path) -> None:
    from html_to_pptx import convert as lib_convert
    await lib_convert(str(input_html), str(output_pptx))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='source HTML slide deck')
    parser.add_argument('output', type=Path, help='output .pptx path')
    parser.add_argument('--zoom', default='auto', help="'auto' (1920/stage width) or an explicit factor")
    parser.add_argument('--no-strip-fonts', action='store_true', help='keep remote font <link>s')
    args = parser.parse_args()

    if not args.input.is_file():
        print(f'input not found: {args.input}')
        return 1

    html = args.input.read_text(encoding='utf-8')

    if not args.no_strip_fonts:
        html = strip_remote_fonts(html)

    # Probe and convert from the SAME stripped tree: the original file may hang
    # its own load on remote fonts.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', suffix='.html', encoding='utf-8', delete=False, dir=args.output.parent) as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)

    try:
        if args.zoom == 'auto':
            detected = detect_stage(tmp_path)
            if not detected:
                print('could not detect a slide stage (no element 800–3000px wide); pass --zoom explicitly')
                return 1
            selector, width = detected
            zoom = CANVAS_WIDTH / width
            print(f'detected stage {selector!r} at {width:.0f}px → zoom {zoom:.4g}')
        else:
            zoom = float(args.zoom)
            detected = detect_stage(tmp_path)
            selector = detected[0] if detected else '.slide'

        with tempfile.NamedTemporaryFile('w', suffix='.html', encoding='utf-8', delete=False, dir=args.output.parent) as tmp2:
            tmp2.write(inject_zoom(html, selector, zoom))
            zoomed_path = Path(tmp2.name)

        try:
            asyncio.run(convert(zoomed_path, args.output))
        finally:
            zoomed_path.unlink(missing_ok=True)
    finally:
        tmp_path.unlink(missing_ok=True)

    print(f'wrote {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
