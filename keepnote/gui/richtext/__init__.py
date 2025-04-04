# Python imports
import codecs
from itertools import chain
import os
import re
import random
import io
import urllib.parse
import uuid
from xml.sax.saxutils import escape
import gi
from gi.overrides import GdkPixbuf

gi.require_version('Gtk', '4.0')
# PyGObject imports (GTK 4)
from gi.repository import Gtk, Gdk, Pango

# Textbuffer_tools imports
from .textbuffer_tools import \
    iter_buffer_contents, iter_buffer_anchors, sanitize_text

# Richtextbuffer imports
from .richtextbuffer import ignore_tag, RichTextBuffer, RichTextImage

# Tag imports
from .richtext_tags import \
    RichTextModTag, \
    RichTextJustifyTag, \
    RichTextFamilyTag, \
    RichTextSizeTag, \
    RichTextFGColorTag, \
    RichTextBGColorTag, \
    RichTextIndentTag, \
    RichTextBulletTag, \
    RichTextLinkTag, \
    get_text_scale

# Pyflakes ignore
RichTextBulletTag
RichTextIndentTag

# Richtext IO
from .richtext_html import HtmlBuffer, HtmlError

import keepnote
from keepnote import translate as _

# Constants
DEFAULT_FONT = "Sans 10"
TEXTVIEW_MARGIN = 5
if keepnote.get_platform() == "darwin":
    CLIPBOARD_NAME = "primary"
else:
    CLIPBOARD_NAME = "clipboard"
RICHTEXT_ID = -3  # Application-defined integer for the clipboard
CONTEXT_MENU_ACCEL_PATH = "<main>/richtext_context_menu"
QUOTE_FORMAT = 'from <a href="%u">%t</a>:<br/>%s'

# MIME types
MIME_RICHTEXT = "application/x-richtext" + str(random.randint(1, 100000))
MIME_IMAGES = ["image/png",
               "image/bmp",
               "image/jpeg",
               "image/xpm",
               "public.png",
               "public.bmp",
               "public.jpeg",
               "public.xpm"]
MIME_TEXT = ["text/plain",
             "text/plain;charset=utf-8",
             "text/plain;charset=UTF-8",
             "UTF8_STRING",
             "STRING",
             "COMPOUND_TEXT",
             "TEXT"]
MIME_HTML = ["text/html"]

# Globals
_g_clipboard_contents = None

def parse_font(fontstr):
    """Parse a font string from the font chooser"""
    tokens = fontstr.split(" ")
    size = int(tokens.pop())
    mods = []
    while tokens[-1] in ["Bold", "Italic"]:
        mods.append(tokens.pop().lower())
    return " ".join(tokens), mods, size

def parse_utf(text):
    if isinstance(text, bytes):
        if (text[:2] in (codecs.BOM_UTF16_BE, codecs.BOM_UTF16_LE) or
                (len(text) > 1 and text[1] == 0) or
                (len(text) > 3 and text[3] == 0)):
            return text.decode("utf16")
        else:
            text = text.replace(b"\x00", b"")
            return text.decode("utf8")
    return text

def parse_ie_html_format(text):
    """Extract HTML from IE's 'HTML Format' clipboard data"""
    index = text.find("<!--StartFragment")
    if index == -1:
        return None
    index = text.find(">", index)
    return text[index+1:]

def parse_ie_html_format_headers(text):
    headers = {}
    for line in text.splitlines():
        if line.startswith("<"):
            break
        i = line.find(":")
        if i == -1:
            break
        key = line[:i]
        val = line[i+1:]
        headers[key] = val
    return headers

def parse_richtext_headers(text):
    headers = {}
    for line in text.splitlines():
        i = line.find(":")
        if i > -1:
            headers[line[:i]] = line[i+1:]
    return headers

def format_richtext_headers(values):
    return "\n".join(key + ":" + val.replace("\n", "") for key, val in values)

def is_relative_file(filename):
    """Returns True if filename is relative"""
    return (not re.match("[^:/]+://", filename) and
            not os.path.isabs(filename))

def replace_vars(text, values):
    textlen = len(text)
    out = []
    i = 0
    while i < textlen:
        if text[i] == "\\" and i < textlen - 1:
            out.append(text[i+1])
            i += 2
        elif text[i] == "%" and i < textlen - 1:
            varname = text[i:i+2]
            out.append(values.get(varname, ""))
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)

# Exceptions
class RichTextError(Exception):
    def __init__(self, msg, error):
        super().__init__(msg)
        self.msg = msg
        self.error = error

    def __str__(self):
        return f"{self.error}\n{self.msg}" if self.error else self.msg

class RichTextMenu(Gtk.PopoverMenu):
    """A popup menu for child widgets in a RichTextView"""
    def __init__(self):
        super().__init__()
        self._child = None

    def set_child(self, child):
        self._child = child

    def get_child(self):
        return self._child

class RichTextIO(object):
    """Read/Writes the contents of a RichTextBuffer to disk"""
    def __init__(self):
        self._html_buffer = HtmlBuffer()

    def save(self, textbuffer, filename, title=None, stream=None):
        self._save_images(textbuffer, filename)
        try:
            buffer_contents = iter_buffer_contents(
                textbuffer, None, None, ignore_tag)
            if stream:
                out = stream
            else:
                out = codecs.open(filename, "w", "utf-8")
            self._html_buffer.set_output(out)
            self._html_buffer.write(buffer_contents,
                                    textbuffer.tag_table,
                                    title=title)
            out.close()
        except IOError as e:
            raise RichTextError(f"Could not save '{filename}'.", e)
        textbuffer.set_modified(False)

    def load(self, textview, textbuffer, filename, stream=None):
        textbuffer.block_signals()
        if textview:
            spell = textview.is_spell_check_enabled()
            textview.enable_spell_check(False)
            textview.set_buffer(None)
        textbuffer.clear()
        err = None
        try:
            if stream:
                infile = stream
            else:
                infile = codecs.open(filename, "r", "utf-8")
            buffer_contents = self._html_buffer.read(infile)
            textbuffer.insert_contents(buffer_contents,
                                       textbuffer.get_start_iter())
            infile.close()
            textbuffer.place_cursor(textbuffer.get_start_iter())
        except (HtmlError, IOError, Exception) as e:
            err = e
            textbuffer.clear()
            if textview:
                textview.set_buffer(textbuffer)
            ret = False
        else:
            self._load_images(textbuffer, filename)
            if textview:
                textview.set_buffer(textbuffer)
            ret = True
        textbuffer.unblock_signals()
        if textview:
            textview.enable_spell_check(spell)
            textview.enable()
        textbuffer.set_modified(False)
        if not ret:
            raise RichTextError(f"Error loading '{filename}'.", err)

    def _load_images(self, textbuffer, html_filename):
        for kind, it, param in iter_buffer_anchors(textbuffer, None, None):
            child, widgets = param
            if isinstance(child, RichTextImage):
                self._load_image(textbuffer, child, html_filename)

    def _save_images(self, textbuffer, html_filename):
        for kind, it, param in iter_buffer_anchors(textbuffer, None, None):
            child, widgets = param
            if isinstance(child, RichTextImage):
                self._save_image(textbuffer, child, html_filename)

    def _load_image(self, textbuffer, image, html_filename):
        image.set_from_file(
            self._get_filename(html_filename, image.get_filename()))

    def _save_image(self, textbuffer, image, html_filename):
        if image.save_needed():
            image.write(self._get_filename(
                html_filename, image.get_filename()))

    def _get_filename(self, html_filename, filename):
        if is_relative_file(filename):
            path = os.path.dirname(html_filename)
            return os.path.join(path, filename)
        return filename

class RichTextDragDrop(object):
    """Manages drag and drop events for a richtext editor"""
    def __init__(self, targets=[]):
        self._acceptable_targets = []
        self._acceptable_targets.extend(targets)

    def append_target(self, target):
        self._acceptable_targets.append(target)

    def extend_targets(self, targets):
        self._acceptable_targets.extend(targets)

    def find_acceptable_target(self, targets):
        for target in self._acceptable_targets:
            if target in targets:
                return target
        return None

class RichTextView(Gtk.TextView):
    """A RichText editor widget"""
    def __init__(self, textbuffer=None):
        super().__init__()
        self._textbuffer = None
        self._buffer_callbacks = []
        self._blank_buffer = RichTextBuffer()
        self._popup_menu = None
        self._html_buffer = HtmlBuffer()
        self._accel_group = None
        self._accel_path = CONTEXT_MENU_ACCEL_PATH
        self.dragdrop = RichTextDragDrop(MIME_IMAGES + ["text/uri-list"] +
                                         MIME_HTML + MIME_TEXT)
        self._quote_format = QUOTE_FORMAT
        self._current_url = ""
        self._current_title = ""

        if textbuffer is None:
            textbuffer = RichTextBuffer()
        self.set_buffer(textbuffer)

        self.set_default_font(DEFAULT_FONT)

        # Spell checker (disabled for now)
        self._spell_checker = None
        self.enable_spell_check(False)

        # Signals
        self.set_wrap_mode(Gtk.WrapMode.WORD)
        self.set_right_margin(TEXTVIEW_MARGIN)
        self.set_left_margin(TEXTVIEW_MARGIN)

        self.connect("key-press-event", self.on_key_press_event)
        self.connect("backspace", self.on_backspace)
        self.connect("button-press-event", self.on_button_press)

        # Drag and drop
        controller = Gtk.DropTarget.new(type=str, actions=Gdk.DragAction.COPY)
        controller.set_formats(Gdk.ContentFormats.new(MIME_IMAGES + ["text/uri-list"] + MIME_HTML + MIME_TEXT))
        controller.connect("drop", self.on_drop)
        controller.connect("motion", self.on_drag_motion)
        self.add_controller(controller)

        # Clipboard
        self.connect("copy-clipboard", lambda w: self._on_copy())
        self.connect("cut-clipboard", lambda w: self._on_cut())
        self.connect("paste-clipboard", lambda w: self._on_paste())

        self.connect("populate-popup", self.on_popup)

        # Popup menus
        self.init_menus()

    def init_menus(self):
        """Initialize popup menus"""
        self._image_menu = RichTextMenu()
        self._image_menu.attach_to_widget(self, lambda w, m: None)

        item = Gtk.MenuItem.new_with_label("Cut")
        item.connect("activate", lambda w: self.emit("cut-clipboard"))
        self._image_menu.append(item)

        item = Gtk.MenuItem.new_with_label("Copy")
        item.connect("activate", lambda w: self.emit("copy-clipboard"))
        self._image_menu.append(item)

        item = Gtk.MenuItem.new_with_label("Delete")
        def func(widget):
            if self._textbuffer:
                self._textbuffer.delete_selection(True, True)
        item.connect("activate", func)
        self._image_menu.append(item)

    def set_buffer(self, textbuffer):
        if self._textbuffer:
            for callback in self._buffer_callbacks:
                self._textbuffer.disconnect(callback)
        if textbuffer:
            super().set_buffer(textbuffer)
        else:
            super().set_buffer(self._blank_buffer)
        self._textbuffer = textbuffer
        if self._textbuffer:
            self._textbuffer.set_default_attr(self.get_default_attributes())
            self._modified_id = self._textbuffer.connect(
                "modified-changed", self._on_modified_changed)
            self._buffer_callbacks = [
                self._textbuffer.connect("font-change", self._on_font_change),
                self._textbuffer.connect("child-added", self._on_child_added),
                self._textbuffer.connect("child-activated", self._on_child_activated),
                self._textbuffer.connect("child-menu", self._on_child_popup_menu),
                self._modified_id
            ]
            self._textbuffer.add_deferred_anchors(self)

    def set_accel_group(self, accel_group):
        self._accel_group = accel_group

    def set_accel_path(self, accel_path):
        self._accel_path = accel_path

    def set_current_url(self, url, title=""):
        self._current_url = url
        self._current_title = title

    def get_current_url(self):
        return self._current_url

    # Keyboard callbacks
    def on_key_press_event(self, textview, event):
        if self._textbuffer is None:
            return False
        keyval = event.get_keyval()[1]  # GTK 4 returns a tuple (success, keyval)
        if keyval == Gdk.KEY_ISO_Left_Tab:
            if self._textbuffer.get_selection_bounds():
                self.unindent()
                return True
        if keyval == Gdk.KEY_Tab:
            it = self._textbuffer.get_iter_at_mark(self._textbuffer.get_insert())
            if self._textbuffer.starts_par(it) or self._textbuffer.get_selection_bounds():
                self.indent()
                return True
        if keyval == Gdk.KEY_Delete:
            it = self._textbuffer.get_iter_at_mark(self._textbuffer.get_insert())
            if (not self._textbuffer.get_selection_bounds() and
                self._textbuffer.starts_par(it) and
                not self._textbuffer.is_insert_allowed(it) and
                self._textbuffer.get_indent(it)[0] > 0):
                self.toggle_bullet("none")
                self.unindent()
                return True
        return False

    def on_backspace(self, textview):
        if not self._textbuffer:
            return
        it = self._textbuffer.get_iter_at_mark(self._textbuffer.get_insert())
        if self._textbuffer.starts_par(it):
            indent, par_type = self._textbuffer.get_indent()
            if indent > 0:
                self.unindent()
                self.stop_emission_by_name("backspace")

    # Callbacks
    def on_button_press(self, widget, event):
        if event.get_button()[1] == 1 and event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            x, y = self.window_to_buffer_coords(Gtk.TextWindowType.TEXT,
                                                int(event.get_position()[1]), int(event.get_position()[2]))
            it = self.get_iter_at_location(x, y)
            if self.click_iter(it):
                self.stop_emission_by_name("button-press-event")

    def click_iter(self, it=None):
        if not self._textbuffer:
            return False
        if it is None:
            it = self._textbuffer.get_insert_iter()
        for tag in chain(it.get_tags(), it.get_toggled_tags(False)):
            if isinstance(tag, RichTextLinkTag):
                self.emit("visit-url", tag.get_href())
                return True
        return False

    # Drag and drop
    def on_drag_motion(self, controller, x, y):
        if not self._textbuffer:
            return False
        target = self.dragdrop.find_acceptable_target(controller.get_formats().get_mime_types())
        if target:
            return True
        return False

    def on_drop(self, controller, value, x, y):
        if not self._textbuffer:
            return False
        target = self.dragdrop.find_acceptable_target(controller.get_formats().get_mime_types())
        if target in MIME_IMAGES:
            pixbuf = controller.get_value(Gdk.Pixbuf)
            if pixbuf is not None:
                image = RichTextImage()
                image.set_from_pixbuf(pixbuf)
                self.insert_image(image)
                return True
        elif target == "text/uri-list":
            uris = parse_utf(value)
            uris = [xx for xx in (uri.strip() for uri in uris.split("\n"))
                    if len(xx) > 0 and xx[0] != "#"]
            links = ['<a href="%s">%s</a> ' % (uri, uri) for uri in uris]
            self.insert_html("<br />".join(links))
            return True
        elif target in MIME_HTML:
            html = parse_utf(value)
            self.insert_html(html)
            return True
        elif target in MIME_TEXT:
            self._textbuffer.insert_at_cursor(value)
            return True
        return False

    # Copy and Paste
    def _on_copy(self):
        clipboard = self.get_clipboard()
        self.stop_emission_by_name('copy-clipboard')
        self.copy_clipboard(clipboard)

    def _on_cut(self):
        clipboard = self.get_clipboard()
        self.stop_emission_by_name('cut-clipboard')
        self.cut_clipboard(clipboard, self.get_editable())

    def _on_paste(self):
        clipboard = self.get_clipboard()
        self.stop_emission_by_name('paste-clipboard')
        self.paste_clipboard(clipboard, None, self.get_editable())

    def copy_clipboard(self, clipboard):
        if not self._textbuffer:
            return
        sel = self._textbuffer.get_selection_bounds()
        if not sel:
            return
        start, end = sel
        contents = list(self._textbuffer.copy_contents(start, end))
        headers = format_richtext_headers([
            ("title", self._current_title),
            ("url", self._current_url)])
        if len(contents) == 1 and contents[0][0] == "anchor" and isinstance(contents[0][2][0], RichTextImage):
            clipboard.set("Image copied")
        else:
            text = start.get_text(end)
            clipboard.set(text)

    def cut_clipboard(self, clipboard, default_editable):
        if not self._textbuffer:
            return
        self.copy_clipboard(clipboard)
        self._textbuffer.delete_selection(True, default_editable)

    def paste_clipboard(self, clipboard, override_location, default_editable):
        if not self._textbuffer:
            return
        it = self._textbuffer.get_iter_at_mark(self._textbuffer.get_insert())
        if not self._textbuffer.is_insert_allowed(it):
            return
        clipboard.read_text_async(None, self._do_paste_text)

    def paste_clipboard_as_text(self):
        clipboard = self.get_clipboard()
        if not self._textbuffer:
            return
        it = self._textbuffer.get_iter_at_mark(self._textbuffer.get_insert())
        if not self._textbuffer.is_insert_allowed(it):
            return
        clipboard.read_text_async(None, self._do_paste_text)

    def paste_clipboard_as_quote(self, plain_text=False):
        clipboard = self.get_clipboard()
        quote_format = self._quote_format
        if not self._textbuffer:
            return
        it = self._textbuffer.get_iter_at_mark(self._textbuffer.get_insert())
        if not self._textbuffer.is_insert_allowed(it):
            return
        url = self._current_url
        title = self._current_title or "unknown source"
        unique = str(uuid.uuid4())
        quote_format = replace_vars(quote_format, {"%u": escape(url),
                                                   "%t": escape(title),
                                                   "%s": unique})
        contents = self.parse_html(quote_format)
        before = []
        after = []
        for i, item in enumerate(contents):
            if item[0] == "text":
                text = item[2]
                if unique in text:
                    j = text.find(unique)
                    before.append(("text", item[1], text[:j]))
                    after = [("text", item[1], text[j+len(unique):])]
                    after.extend(contents[i+1:])
                    break
            before.append(item)
        self._textbuffer.begin_user_action()
        offset1 = it.get_offset()
        if plain_text:
            self.paste_clipboard_as_text()
        else:
            self.paste_clipboard(clipboard, False, True)
        end = self._textbuffer.get_iter_at_mark(self._textbuffer.get_insert())
        start = self._textbuffer.get_iter_at_offset(offset1)
        contents2 = list(iter_buffer_contents(self._textbuffer, start, end))
        self._textbuffer.delete(start, end)
        self._textbuffer.insert_contents(before)
        self._textbuffer.insert_contents(contents2)
        self._textbuffer.insert_contents(after)
        self._textbuffer.end_user_action()

    def _do_paste_text(self, clipboard, task):
        text = clipboard.read_text_finish(task)
        if text is None:
            return
        self._textbuffer.begin_user_action()
        self._textbuffer.delete_selection(False, True)
        self._textbuffer.insert_at_cursor(sanitize_text(text))
        self._textbuffer.end_user_action()
        self.scroll_mark_onscreen(self._textbuffer.get_insert())

    def set_quote_format(self, format):
        self._quote_format = format

    def get_quote_format(self):
        return self._quote_format

    # State
    def is_modified(self):
        if self._textbuffer:
            return self._textbuffer.get_modified()
        return False

    def _on_modified_changed(self, textbuffer):
        self.emit("modified", textbuffer.get_modified())

    def enable(self):
        self.set_sensitive(True)

    def disable(self):
        if self._textbuffer:
            self._textbuffer.handler_block(self._modified_id)
            self._textbuffer.clear()
            self._textbuffer.set_modified(False)
            self._textbuffer.handler_unblock(self._modified_id)
        self.set_sensitive(False)

    # Popup Menus
    def on_popup(self, textview, menu):
        self._popup_menu = menu
        pos = 3
        item = Gtk.MenuItem.new_with_label(_("Paste As Plain Text"))
        item.connect("activate", lambda item: self.paste_clipboard_as_text())
        menu.insert(item, pos)
        item = Gtk.MenuItem.new_with_label(_("Paste As Quote"))
        item.connect("activate", lambda item: self.paste_clipboard_as_quote())
        menu.insert(item, pos+1)
        item = Gtk.MenuItem.new_with_label(_("Paste As Plain Text Quote"))
        item.connect("activate", lambda item: self.paste_clipboard_as_quote(plain_text=True))
        menu.insert(item, pos+2)
        menu.set_accel_path(self._accel_path)
        if self._accel_group:
            menu.set_accel_group(self._accel_group)

    def _on_child_popup_menu(self, textbuffer, child, button, activate_time):
        self._image_menu.set_child(child)
        if isinstance(child, RichTextImage):
            self._image_menu.popup_at_pointer(None)
            self._image_menu.show()

    def _on_child_added(self, textbuffer, child):
        self._add_children()

    def _on_child_activated(self, textbuffer, child):
        self.emit("child-activated", child)

    def get_image_menu(self):
        return self._image_menu

    def get_popup_menu(self):
        return self._popup_menu

    # Actions
    def _add_children(self):
        self._textbuffer.add_deferred_anchors(self)

    def indent(self):
        if self._textbuffer:
            self._textbuffer.indent()

    def unindent(self):
        if self._textbuffer:
            self._textbuffer.unindent()

    def insert_image(self, image, filename="image.png"):
        if self._textbuffer:
            self._textbuffer.insert_image(image, filename)

    def insert_image_from_file(self, imgfile, filename="image.png"):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(imgfile)
        img = RichTextImage()
        img.set_from_pixbuf(pixbuf)
        self.insert_image(img, filename)

    def insert_hr(self):
        if self._textbuffer:
            self._textbuffer.insert_hr()

    def insert_html(self, html):
        if self._textbuffer:
            self._textbuffer.insert_contents(self.parse_html(html))

    def parse_html(self, html):
        contents = list(self._html_buffer.read(
            io.StringIO(html), partial=True, ignore_errors=True))
        for kind, pos, param in contents:
            if kind == "anchor" and isinstance(param[0], RichTextImage):
                img = param[0]
                filename = img.get_filename()
                if filename and (filename.startswith("http:") or filename.startswith("file:")):
                    try:
                        img.set_from_url(filename, "image.png")
                    except:
                        pass
        return contents

    def get_link(self, it=None):
        if self._textbuffer is None:
            return None, None, None
        return self._textbuffer.get_link(it)

    def set_link(self, url="", start=None, end=None):
        if self._textbuffer is None:
            return
        if start is None or end is None:
            tagname = RichTextLinkTag.tag_name(url)
            self._apply_tag(tagname)
            return self._textbuffer.tag_table.lookup(tagname)
        else:
            return self._textbuffer.set_link(url, start, end)

    # Find/Replace
    def forward_search(self, it, text, case_sensitive, wrap=True):
        it = it.copy()
        if not case_sensitive:
            text = text.lower()
        textlen = len(text)
        while True:
            end = it.copy()
            end.forward_chars(textlen)
            text2 = it.get_slice(end)
            if not case_sensitive:
                text2 = text2.lower()
            if text2 == text:
                return it, end
            if not it.forward_char():
                if wrap:
                    return self.forward_search(
                        self._textbuffer.get_start_iter(),
                        text, case_sensitive, False)
                else:
                    return None

    def backward_search(self, it, text, case_sensitive, wrap=True):
        it = it.copy()
        it.backward_char()
        if not case_sensitive:
            text = text.lower()
        textlen = len(text)
        while True:
            end = it.copy()
            end.forward_chars(textlen)
            text2 = it.get_slice(end)
            if not case_sensitive:
                text2 = text2.lower()
            if text2 == text:
                return it, end
            if not it.backward_char():
                if wrap:
                    return self.backward_search(
                        self._textbuffer.get_end_iter(),
                        text, case_sensitive, False)
                else:
                    return None

    def find(self, text, case_sensitive=False, forward=True, next=True):
        if not self._textbuffer:
            return
        it = self._textbuffer.get_iter_at_mark(self._textbuffer.get_insert())
        if forward:
            if next:
                it.forward_char()
            result = self.forward_search(it, text, case_sensitive)
        else:
            result = self.backward_search(it, text, case_sensitive)
        if result:
            self._textbuffer.select_range(result[0], result[1])
            self.scroll_mark_onscreen(self._textbuffer.get_insert())
            return result[0].get_offset()
        else:
            return -1

    def replace(self, text, replace_text, case_sensitive=False, forward=True, next=False):
        if not self._textbuffer:
            return
        pos = self.find(text, case_sensitive, forward, next)
        if pos != -1:
            self._textbuffer.begin_user_action()
            self._textbuffer.delete_selection(True, self.get_editable())
            self._textbuffer.insert_at_cursor(replace_text)
            self._textbuffer.end_user_action()
        return pos

    def replace_all(self, text, replace_text, case_sensitive=False, forward=True):
        if not self._textbuffer:
            return
        found = False
        self._textbuffer.begin_user_action()
        while self.replace(text, replace_text, case_sensitive, forward, False) != -1:
            found = True
        self._textbuffer.end_user_action()
        return found

    # Spell check (disabled for now)
    def can_spell_check(self):
        return False  # GtkSpell not supported in this migration

    def enable_spell_check(self, enabled=True):
        pass  # Not implemented

    def is_spell_check_enabled(self):
        return False

    # Font manipulation
    def _apply_tag(self, tag_name):
        if self._textbuffer:
            self._textbuffer.apply_tag_selected(
                self._textbuffer.tag_table.lookup(tag_name))

    def toggle_font_mod(self, mod):
        if self._textbuffer:
            self._textbuffer.toggle_tag_selected(
                self._textbuffer.tag_table.lookup(
                    RichTextModTag.tag_name(mod)))

    def set_font_mod(self, mod):
        self._apply_tag(RichTextModTag.tag_name(mod))

    def toggle_link(self):
        tag, start, end = self.get_link()
        if not tag:
            tag = self._textbuffer.tag_table.lookup(
                RichTextLinkTag.tag_name(""))
        self._textbuffer.toggle_tag_selected(tag)

    def set_font_family(self, family):
        self._apply_tag(RichTextFamilyTag.tag_name(family))

    def set_font_size(self, size):
        self._apply_tag(RichTextSizeTag.tag_name(size))

    def set_justify(self, justify):
        self._apply_tag(RichTextJustifyTag.tag_name(justify))

    def set_font_fg_color(self, color):
        if self._textbuffer:
            if color:
                self._textbuffer.toggle_tag_selected(
                    self._textbuffer.tag_table.lookup(
                        RichTextFGColorTag.tag_name(color)))
            else:
                self._textbuffer.remove_tag_class_selected(
                    self._textbuffer.tag_table.lookup(
                        RichTextFGColorTag.tag_name("#000000")))

    def set_font_bg_color(self, color):
        if self._textbuffer:
            if color:
                self._textbuffer.toggle_tag_selected(
                    self._textbuffer.tag_table.lookup(
                        RichTextBGColorTag.tag_name(color)))
            else:
                self._textbuffer.remove_tag_class_selected(
                    self._textbuffer.tag_table.lookup(
                        RichTextBGColorTag.tag_name("#000000")))

    def toggle_bullet(self, par_type=None):
        if self._textbuffer:
            self._textbuffer.toggle_bullet_list(par_type)

    def set_font(self, font_name):
        if not self._textbuffer:
            return
        family, mods, size = parse_font(font_name)
        self._textbuffer.begin_user_action()
        self.set_font_family(family)
        self.set_font_size(size)
        for mod in mods:
            self.set_font_mod(mod)
        mod_class = self._textbuffer.tag_table.get_tag_class("mod")
        for tag in mod_class.tags:
            if tag.get_property("name") not in mods:
                self._textbuffer.remove_tag_selected(tag)
        self._textbuffer.end_user_action()

    def _on_font_change(self, textbuffer, font):
        self.emit("font-change", font)

    def get_font(self):
        if self._textbuffer:
            return self._textbuffer.get_font()
        return self._blank_buffer.get_font()

    def set_default_font(self, font):
        try:
            f = Pango.FontDescription(font)
            f.set_size(int(f.get_size() * get_text_scale()))
            provider = Gtk.CssProvider()
            provider.load_from_data(f"*{{\nfont: {font};\n}}".encode('utf-8'))
            self.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except:
            pass

    # Undo/Redo
    def undo(self):
        if self._textbuffer:
            self._textbuffer.undo()
            self.scroll_mark_onscreen(self._textbuffer.get_insert())

    def redo(self):
        if self._textbuffer:
            self._textbuffer.redo()
            self.scroll_mark_onscreen(self._textbuffer.get_insert())