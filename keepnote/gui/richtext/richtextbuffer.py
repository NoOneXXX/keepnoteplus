"""
KeepNote
Richtext buffer class
"""

# Python imports
import os
import tempfile
import urllib.request, urllib.error, urllib.parse
from itertools import chain
import gi
gi.require_version('Gtk', '4.0')
# PyGObject imports (GTK 4)
from gi.repository import Gtk, GObject, Gdk, GdkPixbuf

# KeepNote imports
import keepnote

# Textbuffer imports
from .textbuffer_tools import \
    iter_buffer_contents, \
    iter_buffer_anchors, \
    insert_buffer_contents

# RichText imports
from .richtextbasebuffer import \
    RichTextBaseBuffer, \
    add_child_to_buffer, \
    RichTextAnchor
from .indent_handler import IndentHandler
from .font_handler import \
    FontHandler, RichTextBaseFont

# RichText tags imports
from .richtext_tags import \
    RichTextTagTable, \
    RichTextJustifyTag, \
    RichTextFamilyTag, \
    RichTextSizeTag, \
    RichTextFGColorTag, \
    RichTextBGColorTag, \
    RichTextIndentTag, \
    RichTextLinkTag, \
    color_to_string, \
    get_attr_size

# These tags will not be enumerated by iter_buffer_contents
IGNORE_TAGS = set(["gtkspell-misspelled"])

# Default maximum undo levels
MAX_UNDOS = 100

# String for bullet points
BULLET_STR = "\u2022 "

# NOTE: use a blank user agent for downloading images
# many websites refuse the python user agent
USER_AGENT = ""

# Default color of a richtext background (RGB values for white)
DEFAULT_BGCOLOR = (65535, 65535, 65535)

# Default color for horizontal rule (black)
DEFAULT_HR_COLOR = (0, 0, 0)

def ignore_tag(tag):
    return tag.get_property("name") in IGNORE_TAGS

# TODO: Maybe move somewhere more general
def download_file(url, filename):
    """Download a url to a file 'filename'"""
    try:
        # Open url and download image
        opener = urllib.request.build_opener()
        request = urllib.request.Request(url)
        request.add_header('User-Agent', USER_AGENT)
        infile = opener.open(request)

        outfile = open(filename, "wb")
        outfile.write(infile.read())
        outfile.close()

        return True

    except Exception:
        return False

# RichText child objects
class BaseWidget(Gtk.EventBox):
    """Widgets in RichTextBuffer must support this interface"""
    def __init__(self):
        super().__init__()
        # In GTK 4, use CSS for background color instead of modify_bg
        self.set_css_classes(["richtext-base-widget"])
        # Define CSS in your application if needed:
        # .richtext-base-widget { background-color: rgb(255, 255, 255); }

    def highlight(self):
        pass

    def unhighlight(self):
        pass

    def show(self):
        self.set_visible(True)

class RichTextSep(BaseWidget):
    """Separator widget for a Horizontal Rule"""
    def __init__(self):
        super().__init__()
        self._sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(self._sep)
        self._size = None

        # In GTK 4, use CSS for styling instead of modify_bg/fg
        self._sep.set_css_classes(["richtext-hr"])
        # Define CSS in your application if needed:
        # .richtext-hr { background-color: black; color: black; }

        self.connect("resize", self._on_resize)
        self.connect("notify::parent", self._on_parent_set)

        self._resize_id = None

    def _on_parent_set(self, widget, pspec):
        """Callback for changing parent"""
        if self._resize_id:
            old_parent = self.get_parent()
            if old_parent:
                old_parent.disconnect(self._resize_id)
        parent = self.get_parent()
        if parent:
            self._resize_id = parent.connect("size-allocate",
                                             self._on_size_change)

    def _on_size_change(self, widget, allocation):
        """Callback for parent's changed size allocation"""
        w, h = self.get_desired_size()
        self.set_size_request(w, h)

    def _on_resize(self, widget, width, height):
        """Callback for widget resize"""
        w, h = self.get_desired_size()
        self.set_size_request(w, h)

    def get_desired_size(self):
        """Returns the desired size"""
        HR_HORIZONTAL_MARGIN = 20
        HR_VERTICAL_MARGIN = 10
        parent = self.get_parent()
        if parent:
            self._size = (parent.get_width() - HR_HORIZONTAL_MARGIN,
                          HR_VERTICAL_MARGIN)
        else:
            self._size = (100, HR_VERTICAL_MARGIN)  # Fallback size
        return self._size

class RichTextHorizontalRule(RichTextAnchor):
    def __init__(self):
        super().__init__()

    def add_view(self, view):
        self._widgets[view] = RichTextSep()
        self._widgets[view].show()
        return self._widgets[view]

    def copy(self):
        return RichTextHorizontalRule()

class BaseImage(BaseWidget):
    """Subclasses Gtk.Image to make an Image Widget that can be used within RichTextViews"""
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._img = Gtk.Image(*args, **kwargs)
        self._img.set_visible(True)
        self.set_child(self._img)

    def highlight(self):
        self.drag_highlight()

    def unhighlight(self):
        self.drag_unhighlight()

    def set_from_pixbuf(self, pixbuf):
        self._img.set_from_pixbuf(pixbuf)

    def set_from_stock(self, stock, size):
        # GTK 4 does not support stock icons, use icon names instead
        self._img.set_from_icon_name("image-missing", Gtk.IconSize.NORMAL)

def get_image_format(filename):
    """Returns the image format for a filename"""
    f, ext = os.path.splitext(filename)
    ext = ext.replace(".", "").lower()
    if ext == "jpg":
        ext = "jpeg"
    return ext

class RichTextImage(RichTextAnchor):
    """An Image child widget in a RichTextView"""
    def __init__(self):
        super().__init__()
        self._filename = None
        self._download = False
        self._pixbuf = None
        self._pixbuf_original = None
        self._size = [None, None]
        self._save_needed = False

    def __del__(self):
        for widget in self._widgets.values():
            widget.disconnect_by_func(self._on_image_destroy)
            widget.disconnect_by_func(self._on_clicked)

    def add_view(self, view):
        self._widgets[view] = BaseImage()
        self._widgets[view].connect("destroy", self._on_image_destroy)
        self._widgets[view].connect("button-press-event", self._on_clicked)

        if self._pixbuf is not None:
            self._widgets[view].set_from_pixbuf(self._pixbuf)

        return self._widgets[view]

    def is_valid(self):
        """Did the image successfully load an image"""
        return self._pixbuf is not None

    def set_filename(self, filename):
        """Sets the filename used for saving image"""
        self._filename = filename

    def get_filename(self):
        """Returns the filename used for saving image"""
        return self._filename

    def get_original_pixbuf(self):
        """Returns the pixbuf of the image at its original size (no scaling)"""
        return self._pixbuf_original

    def set_save_needed(self, save):
        """Sets whether image needs to be saved to disk"""
        self._save_needed = save

    def save_needed(self):
        """Returns True if image needs to be saved to disk"""
        return self._save_needed

    def write(self, filename):
        """Write image to file"""
        if self._pixbuf:
            ext = get_image_format(filename)
            self._pixbuf_original.savev(filename, ext, [], [])
            self._save_needed = False

    def write_stream(self, stream, filename="image.png"):
        """Write image to stream"""
        def write(buf):
            stream.write(buf)
            return True
        format = get_image_format(filename)
        self._pixbuf_original.save_to_callbackv(write, format, [], [])
        self._save_needed = False

    def copy(self):
        """Returns a new copy of the image"""
        img = RichTextImage()
        img.set_filename(self._filename)
        img._size = list(self.get_size())

        if self._pixbuf:
            img._pixbuf = self._pixbuf
            img._pixbuf_original = self._pixbuf_original
        else:
            img.set_no_image()

        return img

    # Set image
    def set_from_file(self, filename):
        """Sets the image from a file"""
        if self._filename is None:
            self._filename = os.path.basename(filename)

        try:
            self._pixbuf_original = GdkPixbuf.Pixbuf.new_from_file(filename)
        except Exception:
            self.set_no_image()
        else:
            self._pixbuf = self._pixbuf_original

            if self.is_size_set():
                self.scale(self._size[0], self._size[1], False)

            for widget in self.get_all_widgets().values():
                widget.set_from_pixbuf(self._pixbuf)

    def set_from_stream(self, stream):
        loader = GdkPixbuf.PixbufLoader()
        try:
            loader.write(stream.read())
            loader.close()
            self._pixbuf_original = loader.get_pixbuf()
        except Exception:
            self.set_no_image()
        else:
            self._pixbuf = self._pixbuf_original

            if self.is_size_set():
                self.scale(self._size[0], self._size[1], False)

            for widget in self.get_all_widgets().values():
                widget.set_from_pixbuf(self._pixbuf)

    def set_no_image(self):
        """Set the 'no image' icon"""
        for widget in self.get_all_widgets().values():
            widget.set_from_icon_name("image-missing", Gtk.IconSize.NORMAL)
        self._pixbuf_original = None
        self._pixbuf = None

    def set_from_pixbuf(self, pixbuf, filename=None):
        """Set the image from a pixbuf"""
        if filename is not None:
            self._filename = filename
        self._pixbuf = pixbuf
        self._pixbuf_original = pixbuf

        if self.is_size_set():
            self.scale(self._size[0], self._size[1], True)
        else:
            for widget in self.get_all_widgets().values():
                widget.set_from_pixbuf(self._pixbuf)

    def set_from_url(self, url, filename=None):
        """Set image by url"""
        imgfile = None

        try:
            f, imgfile = tempfile.mkstemp("", "image")
            os.close(f)

            if download_file(url, imgfile):
                self.set_from_file(imgfile)
                if filename is not None:
                    self.set_filename(filename)
                else:
                    self.set_filename(url)
            else:
                raise Exception("Could not download file")
        except Exception:
            self.set_no_image()

        if imgfile and os.path.exists(imgfile):
            os.remove(imgfile)

    # Image Scaling
    def get_size(self, actual_size=False):
        """Returns the size of the image"""
        if actual_size:
            if self._pixbuf_original is not None:
                w, h = self._size
                if w is None:
                    w = self._pixbuf_original.get_width()
                if h is None:
                    h = self._pixbuf_original.get_height()
                return [w, h]
            else:
                return [0, 0]
        else:
            return self._size

    def get_original_size(self):
        return [self._pixbuf_original.get_width(),
                self._pixbuf_original.get_height()]

    def is_size_set(self):
        return self._size[0] is not None or self._size[1] is not None

    def scale(self, width, height, set_widget=True):
        """Scale the image to a new width and height"""
        if not self.is_valid():
            return

        self._size = [width, height]

        if not self.is_size_set():
            if self._pixbuf != self._pixbuf_original:
                self._pixbuf = self._pixbuf_original
                if self._pixbuf is not None and set_widget:
                    for widget in self.get_all_widgets().values():
                        widget.set_from_pixbuf(self._pixbuf)

        elif self._pixbuf_original is not None:
            width2 = self._pixbuf_original.get_width()
            height2 = self._pixbuf_original.get_height()

            if width is None:
                factor = height / float(height2)
                width = int(factor * width2)
            if height is None:
                factor = width / float(width2)
                height = int(factor * height2)

            self._pixbuf = self._pixbuf_original.scale_simple(
                width, height, GdkPixbuf.InterpType.BILINEAR)

            if set_widget:
                for widget in self.get_all_widgets().values():
                    widget.set_from_pixbuf(self._pixbuf)

        if self._buffer is not None:
            self._buffer.set_modified(True)

    # GUI callbacks
    def _on_image_destroy(self, widget):
        for key, value in list(self._widgets.items()):
            if value == widget:
                del self._widgets[key]
                break

    def _on_clicked(self, widget, event):
        """Callback for when image is clicked"""
        button = event.button
        if button == 1:
            widget.grab_focus()
            self.emit("selected")
            if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
                self.emit("activated")
            return True
        elif button == 3:
            self.emit("selected")
            self.emit("popup-menu", button, event.time)
            return True

# Font
class RichTextFont(RichTextBaseFont):
    """Class for representing a font in a simple way"""
    def __init__(self):
        super().__init__()

        self.mods = {}
        self.justify = "left"
        self.family = "Sans"
        self.size = 10
        self.fg_color = ""
        self.bg_color = ""
        self.indent = 0
        self.par_type = "none"
        self.link = None

    def set_font(self, tags, current_tags, tag_table):
        self.family = "Sans"
        self.size = 10
        self.fg_color = ""
        self.bg_color = ""

        tag_set = set(tags)

        mod_class = tag_table.get_tag_class("mod")
        self.mods = {}
        for tag in mod_class.tags:
            self.mods[tag.get_property("name")] = (tag in current_tags or
                                                   tag in tag_set)
        self.mods["tt"] = (self.mods["tt"] or self.family == "Monospace")

        self.justify = "left"

        for tag in chain(tags, current_tags):
            if isinstance(tag, RichTextJustifyTag):
                self.justify = tag.get_justify()
            elif isinstance(tag, RichTextFamilyTag):
                self.family = tag.get_family()
            elif isinstance(tag, RichTextSizeTag):
                self.size = tag.get_size()
            elif isinstance(tag, RichTextFGColorTag):
                self.fg_color = tag.get_color()
            elif isinstance(tag, RichTextBGColorTag):
                self.bg_color = tag.get_color()
            elif isinstance(tag, RichTextIndentTag):
                self.indent = tag.get_indent()
                self.par_type = tag.get_par_indent()
            elif isinstance(tag, RichTextLinkTag):
                self.link = tag

class RichTextBuffer(RichTextBaseBuffer):
    """
    TextBuffer specialized for rich text editing

    It builds upon the features of RichTextBaseBuffer
    - maintains undo/redo stacks

    Additional Features
    - manages specific child widget actions
      - images
      - horizontal rule
    - manages editing of indentation levels and bullet point lists
    - manages "current font" behavior
    """
    __gsignals__ = {
        "child-added": (GObject.SignalFlags.RUN_LAST, None, (object,)),
        "child-activated": (GObject.SignalFlags.RUN_LAST, None, (object,)),
        "child-menu": (GObject.SignalFlags.RUN_LAST, None, (object, object, object)),
        "font-change": (GObject.SignalFlags.RUN_LAST, None, (object,)),
    }

    def __init__(self, table=RichTextTagTable()):
        super().__init__(table)

        # Indentation handler
        self._indent = IndentHandler(self)
        self.connect("ending-user-action",
                     lambda w: self._indent.update_indentation())

        # Font handler
        self.font_handler = FontHandler(self)
        self.font_handler.set_font_class(RichTextFont)
        self.font_handler.connect(
            "font-change",
            lambda w, font: self.emit("font-change", font))

        # Set of all anchors in buffer
        self._anchors = set()
        self._anchors_highlighted = set()
        self._anchors_deferred = set()

    def clear(self):
        """Clear buffer contents"""
        super().clear()
        self._anchors.clear()
        self._anchors_highlighted.clear()
        self._anchors_deferred.clear()

    def insert_contents(self, contents, it=None):
        """Inserts a content stream into the TextBuffer at iter 'it'"""
        if it is None:
            it = self.get_insert_iter()

        self.begin_user_action()
        insert_buffer_contents(self, it,
                               contents,
                               add_child_to_buffer,
                               lookup_tag=lambda name:
                               self.tag_table.lookup(name))
        self.end_user_action()

    def copy_contents(self, start, end):
        """Return a content stream for copying from iter start and end"""
        contents = iter(iter_buffer_contents(self, start, end, ignore_tag))

        for item in contents:
            if item[0] == "begin" and not item[2].can_be_copied():
                end_tag = item[2]
                while not (item[0] == "end" and item[2] == end_tag):
                    item = next(contents)
                    if item[0] not in ("text", "anchor") and \
                       item[2] != end_tag:
                        yield item
                continue
            yield item

    def on_selection_changed(self):
        """Callback for when selection changes"""
        self.highlight_children()

    def on_paragraph_split(self, start, end):
        """Callback for when paragraphs split"""
        if self.is_interactive():
            self._indent.on_paragraph_split(start, end)

    def on_paragraph_merge(self, start, end):
        """Callback for when paragraphs merge"""
        if self.is_interactive():
            self._indent.on_paragraph_merge(start, end)

    def on_paragraph_change(self, start, end):
        """Callback for when paragraph type changes"""
        if self.is_interactive():
            self._indent.on_paragraph_change(start, end)

    def is_insert_allowed(self, it, text=""):
        """Returns True if insertion is allowed at iter 'it'"""
        return (self._indent.is_insert_allowed(it, text) and
                it.can_insert(True))

    def _on_delete_range(self, textbuffer, start, end):
        # Let indent manager prepare the delete (if needed in the future)
        # if self.is_interactive():
        #     self._indent.prepare_delete_range(start, end)

        super()._on_delete_range(textbuffer, start, end)

        for kind, offset, param in iter_buffer_contents(
                self, start, end, ignore_tag):
            if kind == "anchor":
                child = param[0]
                self._anchors.remove(child)
                if child in self._anchors_highlighted:
                    self._anchors_highlighted.remove(child)

    # Indentation interface
    def indent(self, start=None, end=None):
        """Indent paragraph level"""
        self._indent.change_indent(start, end, 1)

    def unindent(self, start=None, end=None):
        """Unindent paragraph level"""
        self._indent.change_indent(start, end, -1)

    def starts_par(self, it):
        """Returns True if iter 'it' starts a paragraph"""
        return self._indent.starts_par(it)

    def toggle_bullet_list(self, par_type=None):
        """Toggle the state of a bullet list"""
        self._indent.toggle_bullet_list(par_type)

    def get_indent(self, it=None):
        return self._indent.get_indent(it)

    # Font handler interface
    def update_current_tags(self, action):
        return self.font_handler.update_current_tags(action)

    def set_default_attr(self, attr):
        return self.font_handler.set_default_attr(attr)

    def get_default_attr(self):
        return self.font_handler.get_default_attr()

    def get_current_tags(self):
        return self.font_handler.get_current_tags()

    def set_current_tags(self, tags):
        return self.font_handler.set_current_tags(tags)

    def can_be_current_tag(self, tag):
        return self.font_handler.can_be_current_tag(tag)

    def toggle_tag_selected(self, tag, start=None, end=None):
        return self.font_handler.toggle_tag_selected(tag, start, end)

    def apply_tag_selected(self, tag, start=None, end=None):
        return self.font_handler.apply_tag_selected(tag, start, end)

    def remove_tag_selected(self, tag, start=None, end=None):
        return self.font_handler.remove_tag_selected(tag, start, end)

    def remove_tag_class_selected(self, tag, start=None, end=None):
        return self.font_handler.remove_tag_class_selected(tag, start, end)

    def clear_tag_class(self, tag, start, end):
        return self.font_handler.clear_tag_class(tag, start, end)

    def clear_current_tag_class(self, tag):
        return self.font_handler.clear_current_tag_class(tag)

    def get_font(self, font=None):
        return self.font_handler.get_font(font)

    # Child actions
    def add_child(self, it, child):
        if isinstance(child, RichTextImage):
            self._determine_image_name(child)

        self._anchors.add(child)
        child.set_buffer(self)
        child.connect("activated", self._on_child_activated)
        child.connect("selected", self._on_child_selected)
        child.connect("popup-menu", self._on_child_popup_menu)
        self.insert_child_anchor(it, child)

        self._anchors_deferred.add(child)
        self.emit("child-added", child)

    def add_deferred_anchors(self, textview):
        """Add anchors that were deferred"""
        for child in self._anchors_deferred:
            if child in self._anchors:
                self._add_child_at_anchor(child, textview)
        self._anchors_deferred.clear()

    def _add_child_at_anchor(self, child, textview):
        if child.get_deleted():
            return

        widget = child.add_view(textview)
        textview.add_child_at_anchor(widget, child)
        child.show()

    def insert_image(self, image, filename="image.png"):
        """Inserts an image into the textbuffer at current position"""
        if image.get_filename() is None:
            image.set_filename(filename)

        self.begin_user_action()
        it = self.get_insert_iter()
        self.add_child(it, image)
        image.show()
        self.end_user_action()

    def insert_hr(self):
        """Insert Horizontal Rule"""
        self.begin_user_action()
        it = self.get_insert_iter()
        hr = RichTextHorizontalRule()
        self.add_child(it, hr)
        self.end_user_action()

    # Image management
    def get_image_filenames(self):
        filenames = []
        for child in self._anchors:
            if isinstance(child, RichTextImage):
                filenames.append(child.get_filename())
        return filenames

    def _determine_image_name(self, image):
        """Determines image filename"""
        if self._is_new_pixbuf(image.get_original_pixbuf()):
            filename, ext = os.path.splitext(image.get_filename())
            filenames = self.get_image_filenames()
            filename2 = keepnote.get_unique_filename_list(filenames,
                                                          filename, ext)
            image.set_filename(filename2)
            image.set_save_needed(True)

    def _is_new_pixbuf(self, pixbuf):
        if pixbuf is None:
            return False

        for child in self._anchors:
            if isinstance(child, RichTextImage):
                if pixbuf == child.get_original_pixbuf():
                    return False
        return True

    # Links
    def get_tag_region(self, it, tag):
        """Get the start and end TextIters for tag occurring at TextIter it"""
        start = it.copy()
        if tag not in it.get_toggled_tags(True):
            start.backward_to_tag_toggle(tag)

        end = it.copy()
        if tag not in it.get_toggled_tags(False):
            end.forward_to_tag_toggle(tag)

        return start, end

    def get_link(self, it=None):
        if it is None:
            sel = self.get_selection_bounds()
            if len(sel) > 0:
                it = sel[0]
            else:
                it = self.get_insert_iter()

        for tag in chain(it.get_tags(), it.get_toggled_tags(False)):
            if isinstance(tag, RichTextLinkTag):
                start, end = self.get_tag_region(it, tag)
                return tag, start, end

        return None, None, None

    def set_link(self, url, start, end):
        if url is None:
            tag = self.tag_table.lookup(RichTextLinkTag.tag_name(""))
            self.font_handler.clear_tag_class(tag, start, end)
            return None
        else:
            tag = self.tag_table.lookup(RichTextLinkTag.tag_name(url))
            self.font_handler.apply_tag_selected(tag, start, end)
            return tag

    # Child callbacks
    def _on_child_selected(self, child):
        """Callback for when child object is selected"""
        it = self.get_iter_at_child_anchor(child)
        end = it.copy()
        end.forward_char()
        self.select_range(it, end)

    def _on_child_activated(self, child):
        """Callback for when child is activated (e.g. double-clicked)"""
        self.emit("child-activated", child)

    def _on_child_popup_menu(self, child, button, activate_time):
        """Callback for when child's menu is visible"""
        self.emit("child-menu", child, button, activate_time)

    def highlight_children(self):
        """Highlight any children that are within selection range"""
        sel = self.get_selection_bounds()

        if len(sel) > 0:
            highlight = set(x[2][0] for x in
                            iter_buffer_anchors(self, sel[0], sel[1]))
            for child in self._anchors_highlighted:
                if child not in highlight:
                    child.unhighlight()
            for child in highlight:
                child.highlight()
            self._anchors_highlighted = highlight
        else:
            for child in self._anchors_highlighted:
                child.unhighlight()
            self._anchors_highlighted.clear()