#!/usr/bin/env python3
"""AG Image Tune — batch soft-glow processor for a folder of images.

Replicates the GIMP plugin 'AGImage' (Filters -> AGImage -> AG Image Tune):
dupe x2 -> desaturate LUMA -> gaussian blur -> invert -> opacity 25 ->
merge down -> opacity 80 -> soft light -> flatten.

Usage:
    python agimage_batch.py <src_folder> <dst_folder>
    python agimage_batch.py <src> <dst> --blur 5.0 --top-opacity 30 --merged-opacity 70
"""
import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def soft_glow(img: Image.Image, blur: float = 3.5,
              top_opacity: float = 25.0, merged_opacity: float = 80.0) -> Image.Image:
    """Apply the AG Image Tune soft-glow effect to a single image."""
    base = img.convert("RGB")
    dup1 = base.copy()

    # Top layer: desaturate (LUMA ~ grayscale) -> gaussian blur -> invert
    top = ImageOps.grayscale(base).convert("RGB")
    top = top.filter(ImageFilter.GaussianBlur(blur))
    top = ImageOps.invert(top)

    # Merge down #1: dup1 with top @ top_opacity (25%)
    merged = Image.blend(dup1, top, top_opacity / 100.0)

    # Flatten: base + merged in SOFT LIGHT mode @ merged_opacity (80%)
    soft = ImageChops.soft_light(base, merged)
    result = Image.blend(base, soft, merged_opacity / 100.0)
    return result


def process_folder(src: str, dst: str, **kwargs) -> None:
    src_p, dst_p = Path(src), Path(dst)
    if not src_p.is_dir():
        print(f"ERROR: source folder not found: {src_p}")
        return
    dst_p.mkdir(parents=True, exist_ok=True)

    files = [f for f in src_p.iterdir()
             if f.is_file() and f.suffix.lower() in SUPPORTED]
    files.sort()
    if not files:
        print("No supported images found (jpg/png/webp/bmp/tif).")
        return

    for i, f in enumerate(files, 1):
        try:
            out = soft_glow(Image.open(f), **kwargs)
            out_path = dst_p / f.name
            out.save(out_path)
            print(f"[{i}/{len(files)}] {f.name} -> {out_path}")
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(files)}] ERROR {f.name}: {e}")

    print(f"Done: {len(files)} image(s) processed.")


def main() -> None:
    p = argparse.ArgumentParser(
        description="AG Image Tune batch soft-glow processor")
    p.add_argument("src", help="Source folder with images")
    p.add_argument("dst", help="Destination folder for processed images")
    p.add_argument("--blur", type=float, default=3.5,
                   help="Gaussian blur radius (default 3.5)")
    p.add_argument("--top-opacity", type=float, default=25.0,
                   help="Top layer opacity after invert, %% (default 25)")
    p.add_argument("--merged-opacity", type=float, default=80.0,
                   help="Merged layer opacity in soft light, %% (default 80)")
    args = p.parse_args()
    process_folder(args.src, args.dst,
                   blur=args.blur,
                   top_opacity=args.top_opacity,
                   merged_opacity=args.merged_opacity)


if __name__ == "__main__":
    main()
