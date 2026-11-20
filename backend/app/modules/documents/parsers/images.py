"""Shared by the readers: turn an embedded picture into a PNG a model can look at, and decide which
pictures are decoration (icons, logos, banner strips) rather than content."""

import io

from PIL import Image

from app.modules.documents.reading import ReaderConfig


def to_png(blob: bytes, max_side: int) -> tuple[bytes, int, int] | None:
    """The picture as an RGB PNG no larger than `max_side` on its long edge, with its original
    pixel size. None when it cannot be decoded (vector formats such as EMF, damaged data)."""
    try:
        with Image.open(io.BytesIO(blob)) as opened:
            width, height = opened.size
            image: Image.Image
            if opened.mode in ("RGBA", "LA", "P"):
                rgba = opened.convert("RGBA")
                image = Image.new("RGB", rgba.size, (255, 255, 255))
                image.paste(rgba, mask=rgba.split()[-1])
            else:
                image = opened.convert("RGB")
            if max(image.size) > max_side:
                image.thumbnail((max_side, max_side))
            out = io.BytesIO()
            image.save(out, format="PNG")
            return out.getvalue(), width, height
    except Exception:  # noqa: BLE001 - any decode failure just means "not usable as an image"
        return None


def looks_decorative(width: int, height: int, cfg: ReaderConfig) -> bool:
    """Too small to carry content, or a thin strip (a banner or divider)."""
    if width < cfg.min_px or height < cfg.min_px:
        return True
    ratio = max(width / height, height / width)
    return ratio > cfg.max_banner_ratio


def repeated_threshold(units: int) -> int:
    """An image that shows up on at least this many pages or slides is a logo or a background,
    not content: a third of them, and never fewer than two."""
    return max(2, -(-units * 3 // 10))
