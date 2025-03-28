# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
gi.require_version('PangoCairo', '1.0')  # Specify PangoCairo 1.0
gi.require_version('Gdk', '3.0')  # Specify Gdk 3.0
gi.require_version('GdkPixbuf', '2.0')  # Specify GdkPixbuf 2.0
gi.require_version('Pango', '1.0')  # Specify Pango 1.0
gi.require_version('GObject', '2.0')  # Specify GObject 2.0
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango, PangoCairo, GObject
import cairo
import keepnote
_ = keepnote.translate

# Constants
FONT_LETTER = "A"

DEFAULT_COLORS_FLOAT = [
    # lights
    (1, .6, .6), (1, .8, .6), (1, 1, .6), (.6, 1, .6), (.6, 1, 1), (.6, .6, 1), (1, .6, 1),
    # trues
    (1, 0, 0), (1, .64, 0), (1, 1, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1), (1, 0, 1),
    # darks
    (.5, 0, 0), (.5, .32, 0), (.5, .5, 0), (0, .5, 0), (0, .5, .5), (0, 0, .5), (.5, 0, .5),
    # white, gray, black
    (1, 1, 1), (.9, .9, .9), (.75, .75, .75), (.5, .5, .5), (.25, .25, .25), (.1, .1, .1), (0, 0, 0),
]

# Color conversion functions
def color_float_to_int8(color):
    return (int(255 * color[0]), int(255 * color[1]), int(255 * color[2]))

def color_float_to_int16(color):
    return (int(65535 * color[0]), int(65535 * color[1]), int(65535 * color[2]))

def color_int16_to_str(color):
    return f"#{color[0]//256:02x}{color[1]//256:02x}{color[2]//256:02x}"

def color_int8_to_str(color):
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

def color_str_to_int16(colorstr):
    return (int(colorstr[1:3], 16) * 256, int(colorstr[3:5], 16) * 256, int(colorstr[5:7], 16) * 256)

DEFAULT_COLORS = [color_int8_to_str(color_float_to_int8(color)) for color in DEFAULT_COLORS_FLOAT]

# ColorTextImage class
class ColorTextImage(Gtk.Image):
    def __init__(self, width, height, letter, border=True):
        super().__init__()
        self.width = width
        self.height = height
        self.letter = letter
        self.border = border
        self.marginx = int((width - 10) / 2.0)
        self.marginy = -int((height - 12) / 2.0)
        self._pixbuf = None
        self.fg_color = None
        self.bg_color = None
        self._exposed = False

        self.connect("parent-set", self.on_parent_set)
        self.connect("draw", self.on_draw)

    def on_parent_set(self, widget, old_parent):
        self._exposed = False

    def on_draw(self, widget, cr):
        if not self._exposed:
            self._exposed = True
            self.init_colors()
        self.do_draw(cr)
        return False

    def init_colors(self):
        self._pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, self.width, self.height)
        self.refresh()

    def set_fg_color(self, color, refresh=True):
        if isinstance(color, str):
            self.fg_color = Gdk.RGBA()
            self.fg_color.parse(color)
        else:
            self.fg_color = color
        if refresh and self._pixbuf:
            self.refresh()

    def set_bg_color(self, color, refresh=True):
        if isinstance(color, str):
            self.bg_color = Gdk.RGBA()
            self.bg_color.parse(color)
        else:
            self.bg_color = color
        if refresh and self._pixbuf:
            self.refresh()

    def refresh(self):
        if not self._pixbuf:
            return
        cr = cairo.Context(self._pixbuf)
        # Fill background
        if self.bg_color:
            Gdk.cairo_set_source_rgba(cr, self.bg_color)
            cr.rectangle(0, 0, self.width, self.height)
            cr.fill()
        # Draw border
        if self.border:
            cr.set_source_rgb(0, 0, 0)
            cr.rectangle(0, 0, self.width - 1, self.height - 1)
            cr.stroke()
        # Draw letter
        if self.letter and self.fg_color:
            layout = PangoCairo.create_layout(cr)
            layout.set_text(FONT_LETTER, -1)
            fontdesc = Pango.FontDescription("Sans Bold 10")
            layout.set_font_description(fontdesc)
            cr.set_source_rgba(self.fg_color.red, self.fg_color.green, self.fg_color.blue, self.fg_color.alpha)
            cr.move_to(self.marginx, self.marginy)
            PangoCairo.show_layout(cr, layout)
        self.set_from_pixbuf(self._pixbuf)

# ColorMenu class
class ColorMenu(Gtk.Menu):
    def __init__(self, colors=DEFAULT_COLORS):
        super().__init__()
        self.width = 7
        self.posi = 4
        self.posj = 0
        self.color_items = []

        no_color = Gtk.MenuItem(label="_Default Color")
        no_color.connect("activate", self.on_no_color)
        self.attach(no_color, 0, self.width, 0, 1)
        no_color.show()

        new_color = Gtk.MenuItem(label="_New Color...")
        new_color.connect("activate", self.on_new_color)
        self.attach(new_color, 0, self.width, 1, 2)
        new_color.show()

        separator = Gtk.SeparatorMenuItem()
        self.attach(separator, 0, self.width, 3, 4)
        separator.show()

        self.set_colors(colors)

    def on_new_color(self, menu):
        dialog = ColorSelectionDialog("Choose color")
        dialog.set_modal(True)
        if dialog.run() == Gtk.ResponseType.OK:
            color = dialog.get_rgba()
            color_str = color_int16_to_str((int(color.red * 65535), int(color.green * 65535), int(color.blue * 65535)))
            if color_str not in self.colors:
                self.colors.append(color_str)
                self.append_color(color_str)
            self.emit("set-colors", self.colors)
            self.emit("set-color", color_str)
        dialog.destroy()

    def on_no_color(self, menu):
        self.emit("set-color", None)

    def clear_colors(self):
        for item in self.color_items:
            self.remove(item)
        self.posi = 4
        self.posj = 0
        self.color_items = []
        self.colors = []

    def set_colors(self, colors):
        self.clear_colors()
        self.colors = list(colors)
        for color in colors:
            self.append_color(color, refresh=False)
        self.show_all()

    def get_colors(self):
        return self.colors

    def append_color(self, color, refresh=True):
        self.add_color(self.posi, self.posj, color, refresh=refresh)
        self.posj += 1
        if self.posj >= self.width:
            self.posj = 0
            self.posi += 1

    def add_color(self, i, j, color, refresh=True):
        item = Gtk.MenuItem()
        img = ColorTextImage(15, 15, False)
        img.set_bg_color(color)
        item.add(img)
        item.connect("activate", lambda w: self.emit("set-color", color))
        self.attach(item, j, j + 1, i, i + 1)
        self.color_items.append(item)
        item.show_all()

GObject.type_register(ColorMenu)
GObject.signal_new("set-color", ColorMenu, GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_PYOBJECT,))
GObject.signal_new("set-colors", ColorMenu, GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_PYOBJECT,))
GObject.signal_new("get-colors", ColorMenu, GObject.SignalFlags.RUN_LAST, None, ())

# ColorTool base class
class ColorTool(Gtk.MenuToolButton):
    def __init__(self, icon, default):
        super().__init__(icon=icon, label="")
        self.icon = icon
        self.color = None
        self.colors = DEFAULT_COLORS
        self.default = default
        self.default_set = True

        self.menu = ColorMenu([])
        self.menu.connect("set-color", self.on_set_color)
        self.menu.connect("set-colors", self.on_set_colors)
        self.set_menu(self.menu)

        self.connect("clicked", self.use_color)
        self.connect("show-menu", self.on_show_menu)

    def on_set_color(self, menu, color):
        raise NotImplementedError("Must be implemented by subclass")

    def on_set_colors(self, menu, colors):
        self.colors = list(colors)
        self.emit("set-colors", self.colors)

    def set_colors(self, colors):
        self.colors = list(colors)
        self.menu.set_colors(colors)

    def get_colors(self):
        return self.colors

    def use_color(self, widget):
        self.emit("set-color", self.color)

    def set_default(self, color):
        self.default = color
        if self.default_set:
            self.icon.set_fg_color(self.default)

    def on_show_menu(self, widget):
        self.emit("get-colors")
        self.menu.set_colors(self.colors)

GObject.type_register(ColorTool)
GObject.signal_new("set-color", ColorTool, GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_PYOBJECT,))
GObject.signal_new("set-colors", ColorTool, GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_PYOBJECT,))
GObject.signal_new("get-colors", ColorTool, GObject.SignalFlags.RUN_LAST, None, ())

# FgColorTool class
class FgColorTool(ColorTool):
    def __init__(self, width, height, default):
        self.icon = ColorTextImage(width, height, True, True)
        self.icon.set_fg_color(default)
        self.icon.set_bg_color("#ffffff")
        super().__init__(self.icon, default)

    def on_set_color(self, menu, color):
        if color is None:
            self.default_set = True
            self.icon.set_fg_color(self.default)
        else:
            self.default_set = False
            self.icon.set_fg_color(color)
        self.color = color
        self.emit("set-color", color)

# BgColorTool class
class BgColorTool(ColorTool):
    def __init__(self, width, height, default):
        self.icon = ColorTextImage(width, height, False, True)
        self.icon.set_bg_color(default)
        super().__init__(self.icon, default)

    def on_set_color(self, menu, color):
        if color is None:
            self.default_set = True
            self.icon.set_bg_color(self.default)
        else:
            self.default_set = False
            self.icon.set_bg_color(color)
        self.color = color
        self.emit("set-color", color)

# ColorSelectionDialog class
class ColorSelectionDialog(Gtk.ColorChooserDialog):
    def __init__(self, title="Choose color"):
        super().__init__(title=title)
        self.set_use_alpha(False)

        vbox = self.get_content_area()
        label = Gtk.Label(label=_("Palette:"))
        label.set_alignment(0, 0.5)
        vbox.pack_start(label, False, False, 0)
        label.show()

        self.palette = ColorPalette(DEFAULT_COLORS)
        self.palette.connect("pick-color", self.on_pick_palette_color)
        vbox.pack_start(self.palette, False, False, 0)
        self.palette.show()

        hbox = Gtk.HButtonBox()
        vbox.pack_start(hbox, False, False, 0)
        hbox.show()

        new_button = Gtk.Button(label="New", stock=Gtk.STOCK_NEW)
        new_button.connect("clicked", self.on_new_color)
        hbox.pack_start(new_button, False, False, 0)
        new_button.show()

        delete_button = Gtk.Button(label="Delete", stock=Gtk.STOCK_DELETE)
        delete_button.connect("clicked", self.on_delete_color)
        hbox.pack_start(delete_button, False, False, 0)
        delete_button.show()

        reset_button = Gtk.Button(label="_Reset", stock=Gtk.STOCK_UNDO)
        reset_button.connect("clicked", self.on_reset_colors)
        hbox.pack_start(reset_button, False, False, 0)
        reset_button.show()

        self.connect("notify::rgba", self.on_color_changed)

    def set_colors(self, colors):
        self.palette.set_colors(colors)

    def get_colors(self):
        return self.palette.get_colors()

    def on_pick_palette_color(self, widget, color):
        rgba = Gdk.RGBA()
        rgba.parse(color)
        self.set_rgba(rgba)

    def on_new_color(self, widget):
        color = self.get_rgba()
        color_str = color_int16_to_str((int(color.red * 65535), int(color.green * 65535), int(color.blue * 65535)))
        self.palette.new_color(color_str)

    def on_delete_color(self, widget):
        self.palette.remove_selected()

    def on_reset_colors(self, widget):
        self.palette.set_colors(DEFAULT_COLORS)

    def on_color_changed(self, widget, pspec):
        color = self.get_rgba()
        color_str = color_int16_to_str((int(color.red * 65535), int(color.green * 65535), int(color.blue * 65535)))
        self.palette.set_color(color_str)

# ColorPalette class
class ColorPalette(Gtk.IconView):
    def __init__(self, colors=DEFAULT_COLORS, nrows=1, ncols=7):
        super().__init__()
        self._model = Gtk.ListStore(GdkPixbuf.Pixbuf, GObject.TYPE_STRING)
        self._cell_size = [30, 20]

        self.set_model(self._model)
        self.set_reorderable(True)
        self.set_columns(ncols)
        self.set_spacing(0)
        self.set_column_spacing(0)
        self.set_row_spacing(0)
        self.set_item_padding(1)
        self.set_margin(1)
        self.set_pixbuf_column(0)

        self.connect("selection-changed", self._on_selection_changed)
        self.set_colors(colors)

    def clear_colors(self):
        self._model.clear()

    def set_colors(self, colors):
        self.clear_colors()
        for color in colors:
            self.append_color(color)

    def get_colors(self):
        colors = []
        self._model.foreach(lambda model, path, iter: colors.append(model.get_value(iter, 1)))
        return colors

    def append_color(self, color):
        width, height = self._cell_size
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, height)
        self._draw_color(pixbuf, color, 0, 0, width, height)
        self._model.append([pixbuf, color])

    def remove_selected(self):
        for path in self.get_selected_items():
            self._model.remove(self._model.get_iter(path))

    def new_color(self, color):
        self.append_color(color)
        n = self._model.iter_n_children()
        self.select_path(Gtk.TreePath.new_from_indices([n - 1]))

    def set_color(self, color):
        width, height = self._cell_size
        it = self._get_selected_iter()
        if it:
            pixbuf = self._model.get_value(it, 0)
            self._draw_color(pixbuf, color, 0, 0, width, height)
            self._model.set_value(it, 1, color)

    def _get_selected_iter(self):
        for path in self.get_selected_items():
            return self._model.get_iter(path)
        return None

    def _on_selection_changed(self, view):
        it = self._get_selected_iter()
        if it:
            color = self._model.get_value(it, 1)
            self.emit("pick-color", color)

    def _draw_color(self, pixbuf, color, x, y, width, height):
        cr = cairo.Context(pixbuf)
        rgba = Gdk.RGBA()
        rgba.parse(color)
        Gdk.cairo_set_source_rgba(cr, rgba)
        cr.rectangle(x, y, width, height)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(x, y, width - 1, height - 1)
        cr.stroke()

GObject.type_register(ColorPalette)
GObject.signal_new("pick-color", ColorPalette, GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,))

# Example usage (optional)
if __name__ == "__main__":
    win = Gtk.Window()
    toolbar = Gtk.Toolbar()
    fg_tool = FgColorTool(20, 20, "#000000")
    bg_tool = BgColorTool(20, 20, "#ffffff")
    toolbar.insert(fg_tool, -1)
    toolbar.insert(bg_tool, -1)
    win.add(toolbar)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()