#!/usr/bin/env python3
# GIMP 3.2 plugin: AG Image Tune — soft-glow effect
# Install: %APPDATA%\GIMP\3.2\plug-ins\agimage\agimage.py
# Menu: Filters -> AGImage -> AG Image Tune
# Verified working on GIMP 3.2.4 / Python 3.14 (Windows 11)
import sys
import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp, GObject, GLib

PROC_NAME = 'agimage'


def run(procedure, config, data):
    # Get image WITHOUT drawable argument (drawable arg breaks execution!)
    images = Gimp.get_images()
    if not images:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

    image = images[0]
    drawable = image.get_selected_layers()[0]

    # 1. Duplicate main layer TWICE -> 3 layers total
    for _ in range(2):
        copy = Gimp.Layer.new_from_drawable(drawable, image)
        copy.set_name(drawable.get_name() + " dup")
        image.insert_layer(copy, None, 0)   # insert on top

    layers = image.get_layers()
    top = layers[0]

    # 2. Desaturate (LUMA model)
    top.desaturate(Gimp.DesaturateMode.LUMA)

    # 3. Gaussian blur 3.5 (GEGL filter API)
    filt = Gimp.DrawableFilter.new(top, "gegl:gaussian-blur")
    cfg = filt.get_config()
    cfg.set_property("std-dev-x", 3.5)
    cfg.set_property("std-dev-y", 3.5)
    top.merge_filter(filt)

    # 4. Invert
    inv = Gimp.DrawableFilter.new(top, "gegl:invert")
    top.merge_filter(inv)

    # 5. Opacity 25
    top.set_opacity(25.0)

    # 6. Merge down
    merged = image.merge_down(top, Gimp.MergeType.CLIP_TO_IMAGE)

    # 7. Opacity 80
    merged.set_opacity(80.0)

    # 8. Mode Soft light
    merged.set_mode(Gimp.LayerMode.SOFTLIGHT)

    # 9. Flatten
    image.flatten()
    image.clean_all()
    Gimp.displays_flush()

    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


class AGImage(Gimp.PlugIn):
    def do_set_i18n(self, name):
        return True, 'gimp30-python', None

    def do_query_procedures(self):
        return [PROC_NAME]

    def do_create_procedure(self, name):
        if name == PROC_NAME:
            procedure = Gimp.Procedure.new(self, name,
                                           Gimp.PDBProcType.PLUGIN,
                                           run, None)
            procedure.set_menu_label("AG Image _Tune")
            procedure.set_documentation("Soft glow: dupe x2, desaturate, blur, invert, soft light",
                                        "Dupe x2, top: desaturate LUMA, blur 3.5, invert, opacity 25, merge down, opacity 80, soft light, flatten",
                                        "")
            procedure.set_attribution("Andrew Golubev", "Andrew Golubev", "2026")
            procedure.set_image_types("RGB*, GRAY*")
            procedure.add_enum_argument("run-mode", "Run mode", "The run mode",
                                        Gimp.RunMode, Gimp.RunMode.NONINTERACTIVE,
                                        GObject.ParamFlags.READWRITE)
            procedure.add_menu_path("<Image>/Filters/AGImage")
            return procedure
        return None


Gimp.main(AGImage.__gtype__, sys.argv)
