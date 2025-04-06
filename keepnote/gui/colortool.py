# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Pango', '1.0')
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

        self.connect("realize", self.on_realize)

    def on_realize(self, widget):
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
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        cr = cairo.Context(surface)
        if self.bg_color:
            Gdk.cairo_set_source_rgba(cr, self.bg_color)
            cr.rectangle(0, 0, self.width, self.height)
            cr.fill()
        if self.border:
            cr.set_source_rgb(0, 0, 0)
            cr.rectangle(0, 0, self.width - 1, self.height - 1)
            cr.stroke()
        if self.letter and self.fg_color:
            layout = PangoCairo.create_layout(cr)
            layout.set_text(FONT_LETTER, -1)
            fontdesc = Pango.FontDescription("Sans Bold 10")
            layout.set_font_description(fontdesc)
            cr.set_source_rgba(self.fg_color.red, self.fg_color.green, self.fg_color.blue, self.fg_color.alpha)
            cr.move_to(self.marginx, self.marginy)
            PangoCairo.show_layout(cr, layout)
        self.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_data(surface.get_data(), GdkPixbuf.Colorspace.RGB, True, 8, self.width, self.height, surface.get_stride()))

    def do_snapshot(self, snapshot):
        if self._pixbuf:
            texture = Gdk.Texture.new_for_pixbuf(self._pixbuf)
            snapshot.append_texture(texture, Gdk.Rectangle(x=0, y=0, width=self.width, height=self.height))

# ColorMenu class
class ColorMenu(Gtk.Popover):
    def __init__(self, colors=DEFAULT_COLORS):
        super().__init__()
        self.width = 7
        self.color_items = []
        self.colors = []

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(self.box)

        # Default color button
        no_color_btn = Gtk.Button(label=_("Default Color"))
        no_color_btn.connect("clicked", self.on_no_color)
        self.box.append(no_color_btn)

        # New color button
        new_color_btn = Gtk.Button(label=_("New Color..."))
        new_color_btn.connect("clicked", self.on_new_color)
        self.box.append(new_color_btn)

        # Separator
        self.box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Grid for color buttons
        self.grid = Gtk.Grid()
        self.grid.set_column_spacing(4)
        self.grid.set_row_spacing(4)
        self.box.append(self.grid)

        self.set_colors(colors)

    def on_new_color(self, button):
        dialog = ColorSelectionDialog("Choose color")
        dialog.set_modal(True)
        dialog.set_transient_for(self.get_root())  # Set parent window
        dialog.connect("response", self.on_color_dialog_response)
        dialog.present()

    def on_color_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            color = dialog.get_rgba()
            color_str = color_int16_to_str((int(color.red * 65535),
                                            int(color.green * 65535),
                                            int(color.blue * 65535)))
            if color_str not in self.colors:
                self.colors.append(color_str)
                self.append_color(color_str)
            self.emit("set-colors", self.colors)
            self.emit("set-color", color_str)
        dialog.destroy()

    def on_no_color(self, button):
        self.emit("set-color", None)

    def clear_colors(self):
        for item in self.color_items:
            self.grid.remove(item)
        self.color_items = []
        self.colors = []

    def set_colors(self, colors):
        self.clear_colors()
        self.colors = list(colors)
        for i, color in enumerate(colors):
            self.append_color(color)

    def append_color(self, color):
        i = len(self.color_items)
        row = i // self.width
        col = i % self.width
        self.add_color(row, col, color)

    def add_color(self, i, j, color):
        button = Gtk.Button()
        img = ColorTextImage(15, 15, False)
        img.set_bg_color(color)
        button.set_child(img)
        button.connect("clicked", lambda w: self.emit("set-color", color))
        self.grid.attach(button, j, i, 1, 1)
        self.color_items.append(button)

GObject.type_register(ColorMenu)
GObject.signal_new("set-color", ColorMenu, GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_PYOBJECT,))
GObject.signal_new("set-colors", ColorMenu, GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_PYOBJECT,))

# ColorTool base class
class ColorTool(Gtk.MenuButton):
    def __init__(self, default):
        super().__init__()
        self.icon = None
        self.color = None
        self.colors = DEFAULT_COLORS
        self.default = default
        self.default_set = True

        self.menu = ColorMenu([])
        self.menu.connect("set-color", self.on_set_color)
        self.menu.connect("set-colors", self.on_set_colors)
        self.set_popover(self.menu)

        self.connect("activate", self.use_color)

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
        super().__init__(default)
        self.set_child(self.icon)

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
        super().__init__(default)
        self.set_child(self.icon)

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

        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.get_content_area().append(main_vbox)

        label = Gtk.Label(label=_("Palette:"))
        label.set_halign(Gtk.Align.START)
        main_vbox.append(label)

        self.palette = ColorPalette(DEFAULT_COLORS)
        self.palette.connect("pick-color", self.on_pick_palette_color)
        main_vbox.append(self.palette)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_vbox.append(hbox)

        new_button = Gtk.Button(label="New")
        new_button.connect("clicked", self.on_new_color)
        hbox.append(new_button)

        delete_button = Gtk.Button(label="Delete")
        delete_button.connect("clicked", self.on_delete_color)
        hbox.append(delete_button)

        reset_button = Gtk.Button(label="_Reset")
        reset_button.connect("clicked", self.on_reset_colors)
        hbox.append(reset_button)

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
class ColorPalette(Gtk.FlowBox):
    def __init__(self, colors=DEFAULT_COLORS, nrows=1, ncols=7):
        super().__init__()
        self._model = Gtk.ListStore(GdkPixbuf.Pixbuf, GObject.TYPE_STRING)
        self._cell_size = [30, 20]

        self.set_max_children_per_line(ncols)
        self.set_column_spacing(0)
        self.set_row_spacing(0)
        self.set_homogeneous(True)

        self.connect("child-activated", self._on_selection_changed)
        self.set_colors(colors)

    def clear_colors(self):
        for child in self.get_children():
            self.remove(child)

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
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        self.append(image)

    def remove_selected(self):
        selected = self.get_selected_children()
        if selected:
            path = self._model.get_path(self._model.get_iter_first())
            for i, child in enumerate(self.get_children()):
                if child in selected:
                    self._model.remove(self._model.get_iter(path[i]))
                    self.remove(child)
                    break

    def new_color(self, color):
        self.append_color(color)
        n = self._model.iter_n_children()
        self.select_child(self.get_child_at_index(n - 1))

    def set_color(self, color):
        width, height = self._cell_size
        selected = self.get_selected_children()
        if selected:
            child = selected[0]
            pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, height)
            self._draw_color(pixbuf, color, 0, 0, width, height)
            child.get_first_child().set_from_pixbuf(pixbuf)
            it = self._model.get_iter_first()
            for i, c in enumerate(self.get_children()):
                if c == child:
                    self._model.set_value(it, 1, color)
                    break
                it = self._model.iter_next(it)

    def _on_selection_changed(self, flowbox, child):
        it = self._model.get_iter_first()
        for i, c in enumerate(self.get_children()):
            if c == child:
                color = self._model.get_value(it, 1)
                self.emit("pick-color", color)
                break
            it = self._model.iter_next(it)

    def _draw_color(self, pixbuf, color, x, y, width, height):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(surface)
        rgba = Gdk.RGBA()
        rgba.parse(color)
        Gdk.cairo_set_source_rgba(cr, rgba)
        cr.rectangle(x, y, width, height)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(x, y, width - 1, height - 1)
        cr.stroke()
        pixbuf.get_pixels()[:] = surface.get_data()

GObject.type_register(ColorPalette)
GObject.signal_new("pick-color", ColorPalette, GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,))

# Example usage (optional)
if __name__ == "__main__":
    win = Gtk.Window()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    fg_tool = FgColorTool(20, 20, "#000000")
    bg_tool = BgColorTool(20, 20, "#ffffff")
    box.append(fg_tool)
    box.append(bg_tool)
    win.set_child(box)
    win.connect("destroy", Gtk.main_quit)
    win.show()
    Gtk.main()