# AG Image Tune — Soft Glow Effect for GIMP 3.2

A one-click **soft-glow / dreamy light** effect for images, available in two
flavors:

1. **GIMP 3.2 plugin** — apply the effect interactively from the Filters menu.
2. **Batch processing script** (Python + Pillow) — apply the same effect to a
   whole folder of images without opening GIMP.

## The Effect

The recipe (recreates the classic *"inverted blur soft-light"* glow):

```
Duplicate layer ×2  →  top layer: Desaturate (LUMA)  →  Gaussian Blur 3.5
→  Invert  →  Opacity 25%  →  Merge down  →  Opacity 80%  →  Mode: Soft Light
→  Flatten
```

The result is a soft, dreamy halo around bright areas — great for portraits,
landscapes, and stylized renders.

## Contents

| File | Purpose |
|---|---|
| [`gimp-plugin/agimage.py`](gimp-plugin/agimage.py) | GIMP 3.2 Python plugin (`Filters → AGImage → AG Image Tune`) |
| [`batch/agimage_batch.py`](batch/agimage_batch.py) | Standalone batch processor (Pillow, no GIMP needed) |
| [`docs/AGIMAGE_PLUGIN.md`](docs/AGIMAGE_PLUGIN.md) | Install & usage guide for the GIMP plugin |
| [`docs/AGIMAGE_BATCH.md`](docs/AGIMAGE_BATCH.md) | Install & usage guide for the batch script |

## Quick Start

**GIMP plugin:**

1. Copy the `gimp-plugin/agimage` folder into your GIMP plug-ins directory
   (see the [plugin guide](docs/AGIMAGE_PLUGIN.md) for the exact path).
2. Restart GIMP.
3. `Filters → AGImage → AG Image Tune`.

**Batch processing:**

```bash
pip install pillow
python batch/agimage_batch.py /path/to/source /path/to/output
```

See the [batch guide](docs/AGIMAGE_BATCH.md) for all options.

## Requirements

- **Plugin:** GIMP **3.2.x** (uses the GIMP 3.0 Python API — will not work on
  GIMP 2.10). Python 3.14 bundled with GIMP 3.2 on Windows; works on Linux/macOS
  builds too.
- **Batch script:** Python 3.9+ and [Pillow](https://pypi.org/project/pillow/)
  (`pip install pillow`).

## Effect Comparison

Both tools implement the same algorithm:

| Step | GIMP plugin | Batch script |
|---|---|---|
| Duplicate ×2 | `Gimp.Layer.new_from_drawable` | `img.copy()` |
| Desaturate | `layer.desaturate(LUMA)` | `ImageOps.grayscale` |
| Blur 3.5 | `gegl:gaussian-blur` | `ImageFilter.GaussianBlur(3.5)` |
| Invert | `gegl:invert` | `ImageOps.invert` |
| Opacity / blend | `set_opacity` + `merge_down` | `Image.blend` |
| Soft Light | `Gimp.LayerMode.SOFTLIGHT` | `ImageChops.soft_light` |

## License

MIT — see [LICENSE](LICENSE). Free to use, modify, and share.

---

Made with ❤️ by [ndrew Golubev]
