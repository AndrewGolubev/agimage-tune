# AG Image Tune — Batch Processing Script

Standalone Python script that applies the same soft-glow effect as the
[GIMP plugin](AGIMAGE_PLUGIN.md) to a **whole folder of images at once** —
no GIMP required.

## Requirements

- Python **3.9+**
- [Pillow](https://pypi.org/project/pillow/) (PIL fork) — `pip install pillow`

## Installation

```bash
pip install pillow
```

If `pip`/`python` are not on your PATH (common on Windows), use the full
path, e.g.:

```powershell
C:\Users\<you>\AppData\Local\Programs\Python\Python314\python.exe -m pip install pillow
```

## Usage

```bash
python agimage_batch.py <src_folder> <dst_folder> [options]
```

- `<src_folder>` — folder containing the images to process.
- `<dst_folder>` — folder where processed images are saved (created if it
  does not exist; original files are never modified).

### Example

```bash
python agimage_batch.py C:\Photos\raw C:\Photos\glow
```

### Options

| Option | Default | Description |
|---|---|---|
| `--blur <radius>` | `3.5` | Gaussian blur radius (larger = softer glow) |
| `--top-opacity <pct>` | `25` | Opacity of the inverted blurred layer (0–100) |
| `--merged-opacity <pct>` | `80` | Opacity of the merged layer in Soft Light mode (0–100) |

### Examples with options

```bash
# Softer glow
python agimage_batch.py C:\Photos\raw C:\Photos\glow --blur 5.0

# More subtle effect
python agimage_batch.py C:\Photos\raw C:\Photos\glow --top-opacity 15 --merged-opacity 60
```

## Supported Formats

`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif`, `.tiff`

Output files keep the original filename and format.

## How It Works

The script replicates the GIMP plugin recipe:

1. Duplicate the image twice (3 layers).
2. Top layer: desaturate (LUMA ≈ grayscale).
3. Gaussian blur (`ImageFilter.GaussianBlur`).
4. Invert (`ImageOps.invert`).
5. Blend top into the middle copy at `--top-opacity` (`Image.blend`).
6. Composite the result over the original in **Soft Light** mode
   (`ImageChops.soft_light`) at `--merged-opacity`.

## Notes

- Only files in the top level of the source folder are processed
  (not recursive).
- Files are processed in alphabetical order; each result is printed as
  `[i/N] filename -> output_path`.
- If an individual file fails (corrupt image, unsupported), the script logs
  `ERROR` and continues with the next file.
- Alpha/transparency is not preserved — images are converted to RGB.
  PNGs with transparency will get a (usually black) flattened background;
  use the GIMP plugin for transparency-sensitive work.

## License

MIT — see the project [LICENSE](../LICENSE).
