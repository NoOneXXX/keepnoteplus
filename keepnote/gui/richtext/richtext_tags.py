"""
KeepNote
TagTable and Tags for RichTextBuffer
"""
import gi
gi.require_version('Gtk', '4.0')
# PyGObject imports (GTK 4)
from gi.repository import Gtk, Pango, Gdk

# RichText imports
from .richtextbase_tags import \
    RichTextBaseTagTable, \
    RichTextTag

# Default indentation sizes
MIN_INDENT = 30 - 6
INDENT_SIZE = 30
BULLET_PAR_INDENT = 12  # Hard-coded for 'Sans 10'
BULLET_FONT_SIZE = 10

def color_to_string(color):
    """Converts a color string to a RGB string (#RRGGBB)"""
    # In GTK 4, color can be a string or Gdk.RGBA
    if isinstance(color, Gdk.RGBA):
        # GTK 4's Gdk.RGBA.to_string() returns rgba(r,g,b,a), we want #RRGGBB
        r = int(color.red * 255)
        g = int(color.green * 255)
        b = int(color.blue * 255)
        return f"#{r:02x}{g:02x}{b:02x}"
    return color  # Assume it's already a string like '#RRGGBB'

def color_tuple_to_string(color):
    """Converts a color tuple (r,g,b) to a RGB string (#RRGGBB)"""
    redstr = hex(color[0])[2:].zfill(2)
    greenstr = hex(color[1])[2:].zfill(2)
    bluestr = hex(color[2])[2:].zfill(2)
    return f"#{redstr}{greenstr}{bluestr}"

_text_scale = 1.0

def get_text_scale():
    """Returns current text scale"""
    global _text_scale
    return _text_scale

def set_text_scale(scale):
    global _text_scale
    _text_scale = scale

def get_attr_size(attr):
    # In GTK 4, TextAttributes are not used; this is a placeholder
    return 10  # Default size in points

class RichTextTagTable(RichTextBaseTagTable):
    """A tag table for a RichTextBuffer"""
    def __init__(self):
        super().__init__()

        # Class sets
        self.new_tag_class("mod", RichTextModTag, exclusive=False)
        self.new_tag_class("justify", RichTextJustifyTag)
        self.new_tag_class("family", RichTextFamilyTag)
        self.new_tag_class("size", RichTextSizeTag)
        self.new_tag_class("fg_color", RichTextFGColorTag)
        self.new_tag_class("bg_color", RichTextBGColorTag)
        self.new_tag_class("indent", RichTextIndentTag)
        self.new_tag_class("bullet", RichTextBulletTag)
        self.new_tag_class("link", RichTextLinkTag)

        # Modification (mod) font tags
        # All of these can be combined
        self.tag_class_add(
            "mod",
            RichTextModTag("bold", weight=Pango.Weight.BOLD))
        self.tag_class_add(
            "mod",
            RichTextModTag("italic", style=Pango.Style.ITALIC))
        self.tag_class_add(
            "mod",
            RichTextModTag("underline", underline=Pango.Underline.SINGLE))
        self.tag_class_add(
            "mod",
            RichTextModTag("strike", strikethrough=True))
        self.tag_class_add(
            "mod",
            RichTextModTag("tt", family="Monospace"))
        self.tag_class_add(
            "mod",
            RichTextModTag("nowrap", wrap_mode=Gtk.WrapMode.NONE))

        # Justify tags
        self.tag_class_add(
            "justify", RichTextJustifyTag("left", justification=Gtk.Justification.LEFT))
        self.tag_class_add(
            "justify", RichTextJustifyTag("center", justification=Gtk.Justification.CENTER))
        self.tag_class_add(
            "justify", RichTextJustifyTag("right", justification=Gtk.Justification.RIGHT))
        self.tag_class_add(
            "justify", RichTextJustifyTag("fill", justification=Gtk.Justification.FILL))

        self.bullet_tag = self.tag_class_add("bullet", RichTextBulletTag())

class RichTextModTag(RichTextTag):
    """A tag that represents orthogonal font modifications:
       bold, italic, underline, nowrap
    """
    def __init__(self, name, **kwargs):
        super().__init__(name)
        for key, value in kwargs.items():
            self.set_property(key, value)

    @classmethod
    def tag_name(cls, mod):
        return mod

    @classmethod
    def get_value(cls, tag_name):
        return tag_name

class RichTextJustifyTag(RichTextTag):
    """A tag that represents text justification"""
    justify2name = {
        Gtk.Justification.LEFT: "left",
        Gtk.Justification.RIGHT: "right",
        Gtk.Justification.CENTER: "center",
        Gtk.Justification.FILL: "fill"
    }

    justify_names = set(["left", "right", "center", "fill"])

    def __init__(self, name, **kwargs):
        super().__init__(name)
        for key, value in kwargs.items():
            self.set_property(key, value)

    def get_justify(self):
        return self.get_property("name")

    @classmethod
    def tag_name(cls, justify):
        return justify

    @classmethod
    def get_value(cls, tag_name):
        return tag_name

    @classmethod
    def is_name(cls, tag_name):
        return tag_name in cls.justify_names

class RichTextFamilyTag(RichTextTag):
    """A tag that represents a font family"""
    def __init__(self, family):
        super().__init__("family " + family)
        self.set_property("family", family)

    def get_family(self):
        return self.get_property("family")

    @classmethod
    def tag_name(cls, family):
        return "family " + family

    @classmethod
    def get_value(cls, tag_name):
        return tag_name.split(" ", 1)[1]

    @classmethod
    def is_name(cls, tag_name):
        return tag_name.startswith("family ")

class RichTextSizeTag(RichTextTag):
    """A tag that represents a font size"""
    def __init__(self, size, scale=1.0):
        super().__init__("size %d" % size)
        self.set_property("size-points", int(size * get_text_scale()))

    def get_size(self):
        return int(self.get_property("size-points") / get_text_scale())

    @classmethod
    def tag_name(cls, size):
        return "size %d" % size

    @classmethod
    def get_value(cls, tag_name):
        return int(tag_name.split(" ", 1)[1])

    @classmethod
    def is_name(cls, tag_name):
        return tag_name.startswith("size ")

class RichTextFGColorTag(RichTextTag):
    """A tag that represents a font foreground color"""
    def __init__(self, color):
        super().__init__("fg_color %s" % color)
        self.set_property("foreground", color)

    def get_color(self):
        # In GTK 4, use foreground-rgba and convert to #RRGGBB
        rgba = self.get_property("foreground-rgba")
        return color_to_string(rgba)

    @classmethod
    def tag_name(cls, color):
        return "fg_color " + color

    @classmethod
    def get_value(cls, tag_name):
        return tag_name.split(" ", 1)[1]

    @classmethod
    def is_name(cls, tag_name):
        return tag_name.startswith("fg_color ")

class RichTextBGColorTag(RichTextTag):
    """A tag that represents a font background color"""
    def __init__(self, color):
        super().__init__("bg_color %s" % color)
        self.set_property("background", color)

    def get_color(self):
        # In GTK 4, use background-rgba and convert to #RRGGBB
        rgba = self.get_property("background-rgba")
        return color_to_string(rgba)

    @classmethod
    def tag_name(cls, color):
        return "bg_color " + color

    @classmethod
    def get_value(cls, tag_name):
        return tag_name.split(" ", 1)[1]

    @classmethod
    def is_name(cls, tag_name):
        return tag_name.startswith("bg_color ")

class RichTextIndentTag(RichTextTag):
    """A tag that represents an indentation level"""
    def __init__(self, indent, par_type="none"):
        if par_type == "bullet":
            par_indent_size = BULLET_PAR_INDENT
            extra_margin = 0
        else:
            par_indent_size = 0
            extra_margin = BULLET_PAR_INDENT

        super().__init__("indent %d %s" % (indent, par_type))
        self.set_property("left-margin", MIN_INDENT + INDENT_SIZE * (indent-1) + extra_margin)
        self.set_property("indent", -par_indent_size)

        self._indent = indent
        self._par_type = par_type

    @classmethod
    def tag_name(cls, indent, par_type="none"):
        return "indent %d %s" % (indent, par_type)

    @classmethod
    def get_value(cls, tag_name):
        tokens = tag_name.split(" ")
        if len(tokens) == 2:
            return int(tokens[1]), "none"
        elif len(tokens) == 3:
            return int(tokens[1]), tokens[2]
        else:
            raise Exception("bad tag name '%s'" % tag_name)

    @classmethod
    def is_name(cls, tag_name):
        return tag_name.startswith("indent ")

    @classmethod
    def make_from_name(cls, tag_name):
        return cls(*cls.get_value(tag_name))

    def get_indent(self):
        return self._indent

    def get_par_indent(self):
        return self._par_type

    def is_par_related(self):
        return True

class RichTextBulletTag(RichTextTag):
    """A tag that represents a bullet point"""
    def __init__(self):
        super().__init__("bullet")

    @classmethod
    def tag_name(cls):
        return "bullet"

    @classmethod
    def get_value(cls, tag_name):
        return tag_name

    @classmethod
    def is_name(cls, tag_name):
        return tag_name.startswith("bullet")

    @classmethod
    def make_from_name(cls, tag_name):
        return cls()

    def can_be_current(self):
        return False

    def can_be_copied(self):
        return False

    def is_par_related(self):
        return True

class RichTextLinkTag(RichTextTag):
    """A tag that represents a hyperlink"""
    LINK_COLOR = "#0000FF"

    def __init__(self, href):
        super().__init__("link %s" % href)
        self.set_property("foreground", self.LINK_COLOR)
        self.set_property("underline", Pango.Underline.SINGLE)
        self._href = href

    def get_href(self):
        return self._href

    def expires(self):
        return True

    @classmethod
    def tag_name(cls, href):
        return "link " + href

    @classmethod
    def get_value(cls, tag_name):
        return tag_name.split(" ", 1)[1]

    @classmethod
    def is_name(cls, tag_name):
        return tag_name.startswith("link ")

# Example usage (optional, for testing)
if __name__ == "__main__":
    win = Gtk.Window()
    textview = Gtk.TextView()
    buffer = textview.get_buffer()
    tag_table = RichTextTagTable()
    buffer.set_tag_table(tag_table)

    # Add some text and apply tags
    buffer.insert(buffer.get_start_iter(), "Hello, world!", -1)
    start, end = buffer.get_bounds()
    bold_tag = tag_table.lookup("bold")
    buffer.apply_tag(bold_tag, start, end)

    win.set_child(textview)
    win.connect("close-request", Gtk.main_quit)
    win.show()
    Gtk.main()