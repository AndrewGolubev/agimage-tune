# AG Image Tune — GIMP 3.2 Plugin

One-click soft-glow effect for GIMP 3.2. Adds a menu entry under
**Filters → AGImage → AG Image Tune**.

## Requirements

- **GIMP 3.2.x** (the plugin uses the new GIMP 3.0 Python API and will **not**
  load in GIMP 2.10).
- No extra Python packages needed — GIMP 3.2 ships with its own Python
  (3.14 on Windows).

## Installation (Windows)

1. **Find your GIMP plug-ins folder.**

   The user-level plug-ins directory is:

   ```
   %APPDATA%\GIMP\3.2\plug-ins
   ```

   In Explorer, paste this into the address bar:

   ```
   %APPDATA%\GIMP\3.2\plug-ins
   ```

   (You can verify the exact paths in GIMP: **Edit → Preferences → Folders →
   Plug-ins**.)

2. **Copy the plugin folder** so that the structure looks like this:

   ```
   %APPDATA%\GIMP\3.2\plug-ins\
   └── agimage\
       └── agimage.py
   ```

   ⚠️ **Important:** the `.py` file **must** sit inside its own subfolder
   named `agimage`. A `.py` file placed directly in `plug-ins\` is silently
   ignored by GIMP 3.2 ("plug-ins must be installed in subdirectories").

3. **Restart GIMP** completely (close and reopen).

4. Open any image and go to **Filters → AGImage → AG Image Tune**.

## Installation (Linux / macOS)

Copy the `agimage` folder into one of your plug-ins directories, e.g.:

```
~/.config/GIMP/3.2/plug-ins/agimage/agimage.py
```

Make it executable:

```bash
chmod +x ~/.config/GIMP/3.2/plug-ins/agimage/agimage.py
```

Restart GIMP and check **Filters → AGImage → AG Image Tune**.

## Usage

1. Open an image in GIMP.
2. **Filters → AGImage → AG Image Tune**.
3. Done — the effect is applied directly (no dialog, no parameters to tweak).

The effect is applied to the currently active image and flattens it, so make
sure you save a copy if you want to keep the original layers.

## What It Does

| # | Step | GIMP 3.2 API used |
|---|---|---|
| 1 | Duplicate the main layer twice (3 layers) | `Gimp.Layer.new_from_drawable` + `image.insert_layer` |
| 2 | Desaturate the top layer (LUMA) | `layer.desaturate(Gimp.DesaturateMode.LUMA)` |
| 3 | Gaussian blur 3.5 | `Gimp.DrawableFilter` + `"gegl:gaussian-blur"` (`std-dev-x/y`) |
| 4 | Invert | `"gegl:invert"` filter |
| 5 | Opacity 25% | `layer.set_opacity(25.0)` |
| 6 | Merge down | `image.merge_down(top, Gimp.MergeType.CLIP_TO_IMAGE)` |
| 7 | Opacity 80% | `merged.set_opacity(80.0)` |
| 8 | Mode: Soft Light | `merged.set_mode(Gimp.LayerMode.SOFTLIGHT)` |
| 9 | Flatten | `image.flatten()` |

## Troubleshooting

**The plugin does not appear in the menu.**

1. Check the folder structure — the file must be in a **subfolder**:
   `plug-ins\agimage\agimage.py` (not `plug-ins\agimage.py`).
2. Delete the plugin cache so GIMP rescans plug-ins:
   ```powershell
   Remove-Item "$env:APPDATA\GIMP\3.2\pluginrc"
   ```
3. Launch GIMP with verbose logging and look for errors:
   ```powershell
   & "$env:LOCALAPPDATA\Programs\GIMP 3\bin\gimp-3.2.exe" --verbose 2>&1 | findstr /i "agimage error traceback"
   ```

**"Execution error: unknown error" when running the filter.**

The script uses the currently active image from `Gimp.get_images()`. If no
image is open, the procedure returns an error — make sure an image is open
before running the filter.

## Notes for Developers

This plugin was written against the **GIMP 3.2.4** Python API, which differs
significantly from GIMP 2.10:

- Use `do_query_procedures()` + `do_create_procedure()` (the old
  `@Gimp.PlugIn.procedure` decorator is gone).
- `Gimp.main(AGImage.__gtype__, sys.argv)` — note the double underscores.
- Do **not** declare `drawable`/`image` procedure arguments for a
  `<Image>/...` menu filter — GIMP 3.2 silently cancels the procedure. Fetch
  the image inside `run()` via `Gimp.get_images()[0]` instead.
- GEGL filters: `"gegl:gaussian-blur"` (props `std-dev-x`, `std-dev-y`),
  `"gegl:invert"`.
- No `set_help()` on procedures — help text goes into the second argument of
  `set_documentation()`.

## License

MIT — see the project [LICENSE](../LICENSE).
