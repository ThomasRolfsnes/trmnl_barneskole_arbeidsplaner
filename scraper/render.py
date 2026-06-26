"""Render PDF pages to e-ink-friendly PNGs for TRMNL."""
from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

# Bump when the render output format changes, to invalidate cached content hashes.
RENDER_VERSION = "1"


def render_pdf_to_image(pdf_bytes: bytes, *, width: int, height: int,
                        page: int = 1, grayscale: bool = True,
                        supersample: int = 2, background: int = 255) -> bytes:
    """Render one PDF page onto a fixed width x height canvas.

    The page is scaled to *contain* (preserving aspect ratio) and centered on a
    white canvas, so the output always matches the device's exact pixel size.
    Rendering is supersampled then downscaled with LANCZOS for crisp text.
    """
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        n_pages = len(pdf)
        idx = max(0, min(page - 1, n_pages - 1))
        page_obj = pdf[idx]
        w_pt, h_pt = page_obj.get_size()
        box_w, box_h = width * supersample, height * supersample
        scale = min(box_w / w_pt, box_h / h_pt)
        bitmap = page_obj.render(scale=scale, draw_annots=True)
        img = bitmap.to_pil().convert("RGB")
    finally:
        pdf.close()

    canvas = Image.new("RGB", (box_w, box_h), (background, background, background))
    canvas.paste(img, ((box_w - img.width) // 2, (box_h - img.height) // 2))
    canvas = canvas.resize((width, height), Image.LANCZOS)
    if grayscale:
        canvas = canvas.convert("L")

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _load_font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # GitHub ubuntu runner
        "/System/Library/Fonts/Supplemental/Arial.ttf",     # macOS
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def placeholder_image(*, width: int, height: int, title: str, subtitle: str,
                      grayscale: bool = True) -> bytes:
    """A simple centered text image, used when no plan is published yet."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    title_font = _load_font(max(28, width // 24))
    sub_font = _load_font(max(18, width // 40))

    def center(text, font, y, fill):
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (bbox[2] - bbox[0])) / 2, y), text, font=font, fill=fill)

    center(title, title_font, height * 0.42, (0, 0, 0))
    center(subtitle, sub_font, height * 0.52, (90, 90, 90))

    if grayscale:
        img = img.convert("L")
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
