import gi
gi.require_version('Gtk', '4.0')
# PyGObject imports (GTK 4)
from gi.repository import Gtk, GObject

# Local imports
from .undo_handler import InsertAction
from .richtextbase_tags import RichTextTag

# Font class
class RichTextBaseFont(object):
    """Class for representing a font in a simple way"""
    def __init__(self):
        self.family = None
        self.size = None
        self.bold = False
        self.italic = False
        self.underline = False
        self.fg_color = None
        self.bg_color = None

    def set_font(self, tags, current_tags, tag_table):
        """Set font properties based on tags and current tags"""
        # Default font properties
        self.family = "Sans"
        self.size = 10
        self.bold = False
        self.italic = False
        self.underline = False
        self.fg_color = None
        self.bg_color = None

        # Apply properties from tags
        for tag in tags:
            if hasattr(tag, 'get_property'):
                if tag.get_property("family"):
                    self.family = tag.get_property("family")
                if tag.get_property("size-points"):
                    self.size = tag.get_property("size-points")
                if tag.get_property("weight") == 700:  # Pango.Weight.BOLD
                    self.bold = True
                if tag.get_property("style") == 2:  # Pango.Style.ITALIC
                    self.italic = True
                if tag.get_property("underline") == 1:  # Pango.Underline.SINGLE
                    self.underline = True
                if tag.get_property("foreground"):
                    self.fg_color = tag.get_property("foreground")
                if tag.get_property("background"):
                    self.bg_color = tag.get_property("background")

        # Apply properties from current_tags
        for tag in current_tags:
            if hasattr(tag, 'get_property'):
                if tag.get_property("family"):
                    self.family = tag.get_property("family")
                if tag.get_property("size-points"):
                    self.size = tag.get_property("size-points")
                if tag.get_property("weight") == 700:
                    self.bold = True
                if tag.get_property("style") == 2:
                    self.italic = True
                if tag.get_property("underline") == 1:
                    self.underline = True
                if tag.get_property("foreground"):
                    self.fg_color = tag.get_property("foreground")
                if tag.get_property("background"):
                    self.bg_color = tag.get_property("background")

class FontHandler(GObject.GObject):
    """Basic RichTextBuffer with the following features

        - manages "current font" behavior
    """
    __gsignals__ = {
        "font-change": (GObject.SignalFlags.RUN_LAST, None, (object,)),
    }

    def __init__(self, textbuffer):
        super().__init__()

        self._buf = textbuffer
        self._current_tags = []
        self._default_attr = None  # GTK 4 still does not use TextAttributes directly
        self._font_class = RichTextBaseFont

        self._insert_mark = self._buf.get_insert()
        self._buf.connect("mark-set", self._on_mark_set)

    # Tag manipulation
    def update_current_tags(self, action):
        """Check if current tags need to be applied due to action"""
        self._buf.begin_user_action()

        if isinstance(action, InsertAction):
            # Apply current style to inserted text if inserted text is at cursor
            if action.cursor_insert and len(action.current_tags) > 0:
                it = self._buf.get_iter_at_offset(action.pos)
                it2 = it.copy()
                it2.forward_chars(action.length)

                for tag in action.current_tags:
                    self._buf.apply_tag(tag, it, it2)

        self._buf.end_user_action()

    def _on_mark_set(self, textbuffer, it, mark):
        if mark is self._insert_mark:
            # If cursor at start of line, pick up opening tags, otherwise closing tags
            opening = it.starts_line()
            self.set_current_tags(
                [x for x in it.get_toggled_tags(opening)
                 if isinstance(x, RichTextTag) and x.can_be_current()])

    def set_default_attr(self, attr):
        self._default_attr = attr

    def get_default_attr(self):
        return self._default_attr

    def get_current_tags(self):
        """Returns the currently active tags"""
        return self._current_tags

    def set_current_tags(self, tags):
        """Sets the currently active tags"""
        self._current_tags = list(tags)
        self.emit("font-change", self.get_font())

    def can_be_current_tag(self, tag):
        return isinstance(tag, RichTextTag) and tag.can_be_current()

    def toggle_tag_selected(self, tag, start=None, end=None):
        """Toggle tag in selection or current tags"""
        self._buf.begin_user_action()

        if start is None:
            it = self._buf.get_selection_bounds()
        else:
            it = [start, end]

        # Toggle current tags
        if self.can_be_current_tag(tag):
            if tag not in self._current_tags:
                self.clear_current_tag_class(tag)
                self._current_tags.append(tag)
            else:
                self._current_tags.remove(tag)

        # Update region
        if len(it) == 2:
            if not it[0].has_tag(tag):
                self.clear_tag_class(tag, it[0], it[1])
                self._buf.apply_tag(tag, it[0], it[1])
            else:
                self._buf.remove_tag(tag, it[0], it[1])

        self._buf.end_user_action()
        self.emit("font-change", self.get_font())

    def apply_tag_selected(self, tag, start=None, end=None):
        """Apply tag to selection or current tags"""
        self._buf.begin_user_action()

        if start is None:
            it = self._buf.get_selection_bounds()
        else:
            it = [start, end]

        # Update current tags
        if self.can_be_current_tag(tag):
            if tag not in self._current_tags:
                self.clear_current_tag_class(tag)
                self._current_tags.append(tag)

        # Update region
        if len(it) == 2:
            self.clear_tag_class(tag, it[0], it[1])
            self._buf.apply_tag(tag, it[0], it[1])
        self._buf.end_user_action()
        self.emit("font-change", self.get_font())

    def remove_tag_selected(self, tag, start=None, end=None):
        """Remove tag from selection or current tags"""
        self._buf.begin_user_action()

        if start is None:
            it = self._buf.get_selection_bounds()
        else:
            it = [start, end]

        # No selection, remove tag from current tags
        if tag in self._current_tags:
            self._current_tags.remove(tag)

        # Update region
        if len(it) == 2:
            self._buf.remove_tag(tag, it[0], it[1])
        self._buf.end_user_action()
        self.emit("font-change", self.get_font())

    def remove_tag_class_selected(self, tag, start=None, end=None):
        """Remove all tags of a class from selection or current tags"""
        self._buf.begin_user_action()

        if start is None:
            it = self._buf.get_selection_bounds()
        else:
            it = [start, end]

        # No selection, remove tag from current tags
        self.clear_current_tag_class(tag)

        # Update region
        if len(it) == 2:
            self.clear_tag_class(tag, it[0], it[1])
        self._buf.end_user_action()
        self.emit("font-change", self.get_font())

    def clear_tag_class(self, tag, start, end):
        """Remove all tags of the same class as 'tag' in region (start, end)"""
        cls = self._buf.get_tag_table().get_class_of_tag(tag)
        if cls is not None and cls.exclusive:
            for tag2 in cls.tags:
                self._buf.remove_tag(tag2, start, end)
        self.emit("font-change", self.get_font())

    def clear_current_tag_class(self, tag):
        """Remove all tags of the same class as 'tag' from current tags"""
        cls = self._buf.get_tag_table().get_class_of_tag(tag)
        if cls is not None and cls.exclusive:
            self._current_tags = [x for x in self._current_tags
                                  if x not in cls.tags]

    # Font management
    def get_font_class(self):
        return self._font_class

    def set_font_class(self, font_class):
        self._font_class = font_class

    def get_font(self, font=None):
        """Returns the active font under the cursor"""
        # Get iter for retrieving font
        it2 = self._buf.get_selection_bounds()

        if len(it2) == 0:
            it = self._buf.get_iter_at_mark(self._buf.get_insert())
        else:
            it = it2[0]
            it.forward_char()

        # Create a set that is fast for querying the existence of tags
        current_tags = set(self._current_tags)

        # Get the tags at the iter
        tags = it.get_tags()

        # Create font object and return
        if font is None:
            font = self.get_font_class()()

        font.set_font(tags, current_tags, self._buf.get_tag_table())
        return font

# Example usage (optional, for testing)
if __name__ == "__main__":
    win = Gtk.Window()
    textview = Gtk.TextView()
    buffer = textview.get_buffer()
    font_handler = FontHandler(buffer)

    # Create some example tags
    tag_bold = buffer.create_tag("bold", weight=700)
    tag_italic = buffer.create_tag("italic", style=2)
    buffer.insert(buffer.get_start_iter(), "Hello, world!", -1)
    font_handler.apply_tag_selected(tag_bold)

    win.set_child(textview)
    win.connect("close-request", Gtk.main_quit)
    win.show()
    Gtk.main()