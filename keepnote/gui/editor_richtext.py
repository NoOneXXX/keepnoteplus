# Python 3 and PyGObject imports
import os
import re
import gi
from gi.overrides import GdkPixbuf

gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk, Gdk

# KeepNote imports
import keepnote
from keepnote import KeepNoteError, is_url, unicode_gtk
from keepnote.notebook import NoteBookError, get_node_url, parse_node_url, is_node_url
from keepnote import notebook as notebooklib
from keepnote.gui import dialog_image_new
from keepnote.gui.richtext import RichTextView, RichTextBuffer, RichTextIO, RichTextError, RichTextImage
from keepnote.gui.richtext.richtext_tags import RichTextLinkTag
from keepnote.gui.icons import lookup_icon_filename
from keepnote.gui.font_selector import FontSelector
from keepnote.gui.colortool import FgColorTool, BgColorTool
from keepnote.gui.linkcomplete import LinkPickerPopup
from keepnote.gui.link_editor import LinkEditor
from keepnote.gui.editor import KeepNoteEditor
from keepnote.gui import (
    CONTEXT_MENU_ACCEL_PATH, DEFAULT_FONT, DEFAULT_COLORS,
    FileChooserDialog, get_resource_pixbuf, Action, ToggleAction,
    add_actions, update_file_preview, dialog_find, dialog_image_resize
)

_ = keepnote.translate

def is_relative_file(filename):
    """Returns True if filename is relative"""
    return (not re.match("[^:/]+://", filename) and
            not os.path.isabs(filename))

def is_local_file(filename):
    """Returns True if filename is a local file (no slashes)"""
    return filename and ("/" not in filename) and ("\\" not in filename)

class NodeIO(RichTextIO):
    """Read/Writes the contents of a RichTextBuffer to disk"""

    def __init__(self):
        super().__init__()
        self._node = None
        self._image_files = set()
        self._saved_image_files = set()

    def set_node(self, node):
        self._node = node

    def save(self, textbuffer, filename, title=None, stream=None):
        """Save buffer contents to file"""
        super().save(textbuffer, filename, title, stream=stream)

    def load(self, textview, textbuffer, filename, stream=None):
        super().load(textview, textbuffer, filename, stream=stream)

    def _load_images(self, textbuffer, html_filename):
        """Load images present in textbuffer"""
        self._image_files.clear()
        super()._load_images(textbuffer, html_filename)

    def _save_images(self, textbuffer, html_filename):
        """Save images present in text buffer"""
        # Reset saved image set
        self._saved_image_files.clear()

        # Don't allow the html file to be deleted
        if html_filename:
            self._saved_image_files.add(os.path.basename(html_filename))

        super()._save_images(textbuffer, html_filename)

        # Delete images not part of the saved set
        self._delete_images(html_filename, self._image_files - self._saved_image_files)
        self._image_files = set(self._saved_image_files)

    def _delete_images(self, html_filename, image_files):
        for image_file in image_files:
            # Only delete an image file if it is local
            if is_local_file(image_file):
                try:
                    self._node.delete_file(image_file)
                except:
                    keepnote.log_error()
                    pass

    def _load_image(self, textbuffer, image, html_filename):
        filename = image.get_filename()
        if filename.startswith("http:/") or filename.startswith("file:/"):
            image.set_from_url(filename)
        elif is_relative_file(filename):
            try:
                infile = self._node.open_file(filename, mode="r")
                image.set_from_stream(infile)
                infile.close()
            except:
                image.set_no_image()
        else:
            image.set_from_file(filename)

        # Record loaded images
        self._image_files.add(image.get_filename())

    def _save_image(self, textbuffer, image, html_filename):
        if image.save_needed():
            out = self._node.open_file(image.get_filename(), mode="w")
            image.write_stream(out, image.get_filename())
            out.close()

        # Mark image as saved
        self._saved_image_files.add(image.get_filename())

class RichTextEditor(KeepNoteEditor):
    """Rich text editor for KeepNote"""

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        self._notebook = None

        self._link_picker = None
        self._maxlinks = 10  # Maximum number of links to show in link picker

        # State
        self._page = None
        self._page_scrolls = {}
        self._page_cursors = {}
        self._textview_io = NodeIO()

        # Editor
        self.connect("make-link", self._on_make_link)

        # Textview and its callbacks
        self._textview = RichTextView(RichTextBuffer(self._app.get_richtext_tag_table()))
        self._textview.disable()
        self._textview.connect("font-change", self._on_font_callback)
        self._textview.connect("modified", self._on_modified_callback)
        self._textview.connect("child-activated", self._on_child_activated)
        self._textview.connect("visit-url", self._on_visit_url)
        self._textview.get_buffer().connect("end-user-action", self._on_text_changed)
        self._textview.connect("key-press-event", self._on_key_press_event)

        # Scrollbars
        self._sw = Gtk.ScrolledWindow()
        self._sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._sw.set_has_frame(True)  # Replaces set_shadow_type
        self._sw.set_child(self._textview)  # Changed from add to set_child
        self.append(self._sw)  # Changed from pack_start to append

        # Link editor
        self._link_editor = LinkEditor()
        self._link_editor.set_textview(self._textview)
        self._link_editor.set_search_nodes(self._search_nodes)
        self.connect("font-change", self._link_editor.on_font_change)
        self.append(self._link_editor)  # Changed from pack_start to append

        self.make_image_menu(self._textview.get_image_menu())

        # Menus
        self.editor_menus = EditorMenus(self._app, self)
        self.connect("font-change", self.editor_menus.on_font_change)

        # Find dialog
        self.find_dialog = dialog_find.KeepNoteFindDialog(self)

    def set_notebook(self, notebook):
        """Set notebook for editor"""
        self._notebook = notebook
        if self._notebook:
            self.load_notebook_preferences()
        else:
            self.clear_view()

    def get_notebook(self):
        """Returns notebook"""
        return self._notebook

    def load_preferences(self, app_pref, first_open=False):
        """Load application preferences"""
        self.editor_menus.enable_spell_check(
            app_pref.get("editors", "general", "spell_check", default=True))

        try:
            format = app_pref.get("editors", "general", "quote_format")
            self._textview.set_quote_format(format)
        except:
            pass

        self.load_notebook_preferences()

    def save_preferences(self, app_pref):
        """Save application preferences"""
        app_pref.set("editors", "general", "spell_check",
                     self._textview.is_spell_check_enabled())
        app_pref.set("editors", "general", "quote_format",
                     self._textview.get_quote_format())

    def load_notebook_preferences(self):
        """Load notebook-specific preferences"""
        if self._notebook:
            self._textview.set_default_font(
                self._notebook.pref.get("default_font", default=DEFAULT_FONT))

    def is_focus(self):
        """Return True if text editor has focus"""
        return self._textview.has_focus()

    def grab_focus(self):
        """Pass focus to textview"""
        self._textview.grab_focus()

    def clear_view(self):
        """Clear editor view"""
        self._page = None
        self._textview.disable()

    def undo(self):
        """Undo the last action in the viewer"""
        self._textview.undo()

    def redo(self):
        """Redo the last action in the viewer"""
        self._textview.redo()

    def view_nodes(self, nodes):
        """View a page in the editor"""
        if len(nodes) > 1:
            nodes = []

        self.save()
        self._save_cursor()

        pages = [node for node in nodes if node.get_attr("content_type") == notebooklib.CONTENT_TYPE_PAGE]

        if not pages:
            self.clear_view()
        else:
            page = pages[0]
            self._page = page
            self._textview.enable()

            try:
                self._textview.set_current_url(page.get_url(), title=page.get_title())
                self._textview_io.set_node(self._page)
                self._textview_io.load(
                    self._textview,
                    self._textview.get_buffer(),
                    self._page.get_page_file(),
                    stream=self._page.open_file(self._page.get_page_file(), "r", "utf-8")
                )
                self._load_cursor()
            except RichTextError as e:
                self.clear_view()
                self.emit("error", e.msg, e)
            except Exception as e:
                self.clear_view()
                self.emit("error", "Unknown error", e)

        if pages:
            self.emit("view-node", pages[0])

    def _save_cursor(self):
        if self._page is not None:
            it = self._textview.get_buffer().get_iter_at_mark(self._textview.get_buffer().get_insert())
            self._page_cursors[self._page] = it.get_offset()

            x, y = self._textview.window_to_buffer_coords(Gtk.TextWindowType.TEXT, 0, 0)
            it = self._textview.get_iter_at_location(x, y)
            self._page_scrolls[self._page] = it.get_offset()

    def _load_cursor(self):
        if self._page in self._page_cursors:
            offset = self._page_cursors[self._page]
            it = self._textview.get_buffer().get_iter_at_offset(offset)
            self._textview.get_buffer().place_cursor(it)

        if self._page in self._page_scrolls:
            offset = self._page_scrolls[self._page]
            buf = self._textview.get_buffer()
            it = buf.get_iter_at_offset(offset)
            mark = buf.create_mark(None, it, True)
            self._textview.scroll_to_mark(mark, 0.49, True, 0.0, 0.0)
            buf.delete_mark(mark)

    def save(self):
        """Save the loaded page"""
        if self._page is not None and self._page.is_valid() and self._textview.is_modified():
            try:
                self._textview_io.save(
                    self._textview.get_buffer(),
                    self._page.get_page_file(),
                    self._page.get_title(),
                    stream=self._page.open_file(self._page.get_page_file(), "w", "utf-8")
                )
                self._page.set_attr_timestamp("modified_time")
                self._page.save()
            except (RichTextError, NoteBookError) as e:
                self.emit("error", e.msg, e)

    def save_needed(self):
        """Returns True if textview is modified"""
        return self._textview.is_modified()

    def add_ui(self, window):
        self._textview.set_accel_group(window.get_accel_group())
        self._textview.set_accel_path(CONTEXT_MENU_ACCEL_PATH)
        self._textview.get_image_menu().set_accel_group(window.get_accel_group())
        self.editor_menus.add_ui(window)

    def remove_ui(self, window):
        self.editor_menus.remove_ui(window)

    # Callbacks for textview
    def _on_font_callback(self, textview, font):
        self.emit("font-change", font)
        self._check_link(False)

    def _on_modified_callback(self, textview, modified):
        self.emit("modified", self._page, modified)
        if modified:
            self._page.mark_modified()
            self._page.notify_change(False)

    def _on_child_activated(self, textview, child):
        self.emit("child-activated", textview, child)

    def _on_text_changed(self, textview):
        self._check_link()

    def _on_key_press_event(self, textview, event):
        if (self._link_picker and self._link_picker.shown() and
                event.keyval in (Gdk.KEY_Down, Gdk.KEY_Up, Gdk.KEY_Return, Gdk.KEY_Escape)):
            return self._link_picker.on_key_press_event(textview, event)
        return False

    def _on_visit_url(self, textview, url):
        if is_node_url(url):
            host, nodeid = parse_node_url(url)
            node = self._notebook.get_node_by_id(nodeid)
            if node:
                self.emit("visit-node", node)
        else:
            try:
                self._app.open_webpage(url)
            except KeepNoteError as e:
                self.emit("error", e.msg, e)

    def _on_make_link(self, editor):
        self._link_editor.edit()

    # Callback for link editor
    def _search_nodes(self, text):
        nodes = [(nodeid, title) for nodeid, title in self._notebook.search_node_titles(text)]
        return nodes

    # Link auto-complete
    def _check_link(self, popup=True):
        tag, start, end = self._textview.get_link()
        if tag is not None and popup:
            text = start.get_text(end)
            results = []
            for nodeid, title in self._notebook.search_node_titles(text)[:self._maxlinks]:
                icon = self._notebook.get_attr_by_id(nodeid, "icon")
                if icon is None:
                    icon = "note.png"
                icon = lookup_icon_filename(self._notebook, icon)
                if icon is None:
                    icon = lookup_icon_filename(self._notebook, "note.png")
                pb = keepnote.gui.get_pixbuf(icon)
                results.append((get_node_url(nodeid), title, pb))

            if is_url(text):
                results = [(text, text, get_resource_pixbuf("node_icons", "web.png"))] + results

            if self._link_picker is None:
                self._link_picker = LinkPickerPopup(self._textview)
                self._link_picker.connect("pick-link", self._on_pick_link)

            self._link_picker.set_links(results)

            if results:
                rect = self._textview.get_iter_location(start)
                x, y = self._textview.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, rect.x, rect.y)
                rect = self._textview.get_iter_location(end)
                _, y_end = self._textview.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, rect.x, rect.y)
                self._link_picker.move_on_parent(x, y + rect.height, y_end)
        elif self._link_picker:
            self._link_picker.set_links([])

    def _on_pick_link(self, widget, title, url):
        tag, start, end = self._textview.get_link()
        tagname = RichTextLinkTag.tag_name(url)
        tag = self._textview.get_buffer().tag_table.lookup(tagname)

        offset = start.get_offset()
        self._textview.get_buffer().delete(start, end)

        it = self._textview.get_buffer().get_iter_at_offset(offset)
        self._textview.get_buffer().place_cursor(it)
        self._textview.get_buffer().insert_at_cursor(title)

        end = self._textview.get_buffer().get_iter_at_mark(self._textview.get_buffer().get_insert())
        start = self._textview.get_buffer().get_iter_at_offset(offset)

        self._textview.set_link(url, start, end)
        self._textview.get_buffer().font_handler.clear_current_tag_class(tag)

    # Image/screenshot actions
    def on_screenshot(self):
        if self._page is None:
            return

        imgfile = ""
        self.emit("window-request", "minimize")

        try:
            imgfile = self._app.take_screenshot("keepnote")
            self.emit("window-request", "restore")
            self.insert_image(imgfile, "screenshot.png")
        except Exception as e:
            self.emit("window-request", "restore")
            self.emit("error", _("The screenshot program encountered an error:\n %s") % str(e), e)

        try:
            if os.path.exists(imgfile):
                os.remove(imgfile)
        except OSError as e:
            self.emit("error", _("%s was unable to remove temp file for screenshot") % keepnote.PROGRAM_NAME)

    def on_insert_hr(self):
        if self._page is None:
            return
        self._textview.insert_hr()

    def on_insert_image(self):
        if self._page is None:
            return

        dialog = FileChooserDialog(
            _("Insert Image From File"), self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN,
            app=self._app,
            persistent_path="insert_image_path"
        )
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("_Insert"), Gtk.ResponseType.OK)

        # Add image filters
        filter = Gtk.FileFilter()
        filter.set_name("Images")
        filter.add_mime_type("image/png")
        filter.add_mime_type("image/jpeg")
        filter.add_mime_type("image/gif")
        filter.add_pattern("*.png")
        filter.add_pattern("*.jpg")
        filter.add_pattern("*.gif")
        filter.add_pattern("*.tif")
        filter.add_pattern("*.xpm")
        dialog.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        dialog.add_filter(filter)

        # Setup preview
        preview = Gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.connect("update-preview", update_file_preview, preview)

        dialog.present()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filename = unicode_gtk(dialog.get_filename())
            dialog.destroy()
            if filename is None:
                return

            imgname, ext = os.path.splitext(os.path.basename(filename))
            if ext.lower() in (".jpg", ".jpeg"):
                ext = ".jpg"
            else:
                ext = ".png"

            imgname2 = self._page.new_filename(imgname, ext=ext)

            try:
                self.insert_image(filename, imgname2)
            except Exception as e:
                self.emit("error", _("Could not insert image '%s'") % filename, e)
        else:
            dialog.destroy()

    def insert_image(self, filename, savename="image.png"):
        if self._page is None:
            return

        img = RichTextImage()
        img.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file(filename))
        self._textview.insert_image(img, savename)

    # Image context menu
    def view_image(self, image_filename):
        if self._page is None:
            return

        image_path = os.path.join(self._page.get_path(), image_filename)
        self._app.run_external_app("image_viewer", image_path)

    def _on_view_image(self, menuitem):
        image_filename = menuitem.get_parent().get_child().get_filename()
        self.view_image(image_filename)

    def _on_edit_image(self, menuitem):
        if self._page is None:
            return

        image_filename = menuitem.get_parent().get_child().get_filename()
        image_path = os.path.join(self._page.get_path(), image_filename)
        self._app.run_external_app("image_editor", image_path)

    def _on_resize_image(self, menuitem):
        if self._page is None:
            return

        image = menuitem.get_parent().get_child()
        image_resize_dialog = dialog_image_resize.ImageResizeDialog(self.get_toplevel(), self._app.pref)
        image_resize_dialog.on_resize(image)

    def _on_new_image(self):
        if self._page is None:
            return

        dialog = dialog_image_new.NewImageDialog(self, self._app)
        dialog.show()

    def _on_save_image_as(self, menuitem):
        if self._page is None:
            return

        image = menuitem.get_parent().get_child()

        dialog = FileChooserDialog(
            _("Save Image As..."), self.get_toplevel(),
            action=Gtk.FileChooserAction.SAVE,
            app=self._app,
            persistent_path="save_image_path"
        )
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("_Save"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.present()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            if not dialog.get_filename():
                self.emit("error", _("Must specify a filename for the image."), None)
            else:
                filename = unicode_gtk(dialog.get_filename())
                try:
                    image.write(filename)
                except Exception:
                    self.emit("error", _("Could not save image '%s'.") % filename, None)
        dialog.destroy()

    def make_image_menu(self, menu):
        """Image context menu"""
        menu.set_accel_path(CONTEXT_MENU_ACCEL_PATH)
        item = Gtk.SeparatorMenuItem()
        menu.append(item)

        item = Gtk.MenuItem(label=_("_View Image..."))
        item.connect("activate", self._on_view_image)
        item.get_child().set_label(_("<b>_View Image...</b>"))  # Changed from set_markup_with_mnemonic
        menu.append(item)

        item = Gtk.MenuItem(label=_("_Edit Image..."))
        item.connect("activate", self._on_edit_image)
        menu.append(item)

        item = Gtk.MenuItem(label=_("_Resize Image..."))
        item.connect("activate", self._on_resize_image)
        menu.append(item)

        item = Gtk.MenuItem(label=_("_Save Image As..."))
        item.connect("activate", self._on_save_image_as)
        menu.append(item)

class FontUI:
    def __init__(self, widget, signal, update_func=lambda ui, font: None, block=None, unblock=None):
        self.widget = widget
        self.signal = signal
        self.update_func = update_func

        if block is None:
            self.block = lambda: self.widget.handler_block(self.signal)
        else:
            self.block = block

        if unblock is None:
            self.unblock = lambda: self.widget.handler_unblock(self.signal)
        else:
            self.unblock = unblock

class EditorMenus:
    def __init__(self, app, editor):
        self._editor = editor
        self._app = app
        self._action_group = None
        self._uis = []
        self._font_ui_signals = []
        self.spell_check_toggle = None
        self._removed_widgets = []

    def on_font_change(self, editor, font):
        for ui in self._font_ui_signals:
            ui.block()
        for ui in self._font_ui_signals:
            ui.update_func(ui, font)
        for ui in self._font_ui_signals:
            ui.unblock()

    # Font changing handlers
    def _on_mod(self, mod):
        self._editor.get_textview().toggle_font_mod(mod)

    def _on_toggle_link(self):
        textview = self._editor.get_textview()
        textview.toggle_link()
        tag, start, end = textview.get_link()
        if tag is not None:
            url = start.get_text(end)
            if tag.get_href() == "" and is_url(url):
                textview.set_link(url, start, end)
            self._editor.emit("make-link")

    def _on_justify(self, justify):
        self._editor.get_textview().set_justify(justify)

    def _on_bullet_list(self):
        self._editor.get_textview().toggle_bullet()

    def _on_indent(self):
        self._editor.get_textview().indent()

    def _on_unindent(self):
        self._editor.get_textview().unindent()

    def _on_family_set(self, font_family_combo):
        self._editor.get_textview().set_font_family(font_family_combo.get_family())
        self._editor.get_textview().grab_focus()

    def _on_font_size_change(self, size):
        self._editor.get_textview().set_font_size(size)
        self._editor.get_textview().grab_focus()

    def _on_font_size_inc(self):
        font = self._editor.get_textview().get_font()
        font.size += 2
        self._editor.get_textview().set_font_size(font.size)

    def _on_font_size_dec(self):
        font = self._editor.get_textview().get_font()
        if font.size > 4:
            font.size -= 2
        self._editor.get_textview().set_font_size(font.size)

    def _on_color_set(self, kind, widget, color=0):
        if color == 0:
            color = widget.color
        if kind == "fg":
            self._editor.get_textview().set_font_fg_color(color)
        elif kind == "bg":
            self._editor.get_textview().set_font_bg_color(color)
        else:
            raise Exception(f"unknown color type '{kind}'")

    def _on_colors_set(self, colors):
        notebook = self._editor._notebook
        if notebook:
            notebook.pref.set("colors", list(colors))
            notebook.set_preferences_dirty()
        self._app.get_listeners("colors_changed").notify(notebook, colors)

    def _on_choose_font(self):
        font = self._editor.get_textview().get_font()
        dialog = Gtk.FontChooserDialog(title=_("Choose Font"))
        dialog.set_font(f"{font.family} {font.size}")
        dialog.present()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            font_desc = dialog.get_font()
            self._editor.get_textview().set_font(font_desc)
            self._editor.get_textview().grab_focus()
        dialog.destroy()

    # Spellcheck
    def enable_spell_check(self, enabled):
        self._editor.get_textview().enable_spell_check(enabled)
        enabled = self._editor.get_textview().is_spell_check_enabled()
        if self.spell_check_toggle:
            self.spell_check_toggle.set_active(enabled)
        return enabled

    def on_spell_check_toggle(self, widget):
        self.enable_spell_check(widget.get_active())

    # Toolbar and menus
    def add_ui(self, window):
        # Note: Gtk.UIManager is deprecated in GTK 4. This method needs to be reimplemented
        # using a different approach, such as GMenu or manual widget creation.
        # For now, we'll comment out the implementation and note the need for refactoring.
        print("Warning: add_ui needs to be reimplemented for GTK 4 (Gtk.UIManager is deprecated)")
        pass

    def remove_ui(self, window):
        # Similarly, this method needs to be reimplemented for GTK 4.
        print("Warning: remove_ui needs to be reimplemented for GTK 4 (Gtk.UIManager is deprecated)")
        pass

    def get_actions(self):
        def BothAction(name1, *args):
            return [Action(name1, *args), ToggleAction(name1 + " Tool", *args)]

        return (
            [Action(*x) for x in [
                ("Insert Horizontal Rule", None, _("Insert _Horizontal Rule"), "<control>H", None,
                 lambda w: self._editor.on_insert_hr()),
                ("Insert Image", None, _("Insert _Image..."), "", None,
                 lambda w: self._editor.on_insert_image()),
                ("Insert New Image", None, _("Insert _New Image..."), "", _("Insert a new image"),
                 lambda w: self._on_new_image()),
                ("Insert Screenshot", None, _("Insert _Screenshot..."), "<control>Insert", None,
                 lambda w: self._editor.on_screenshot()),
                ("Find In Page", "gtk-find", _("_Find In Page..."), "<control>F", None,
                 lambda w: self._editor.find_dialog.on_find(False)),
                ("Find Next In Page", "gtk-find", _("Find _Next In Page..."), "<control>G", None,
                 lambda w: self._editor.find_dialog.on_find(False, forward=True)),
                ("Find Previous In Page", "gtk-find", _("Find Pre_vious In Page..."), "<control><shift>G", None,
                 lambda w: self._editor.find_dialog.on_find(False, forward=False)),
                ("Replace In Page", "gtk-find-and-replace", _("_Replace In Page..."), "<control>R", None,
                 lambda w: self._editor.find_dialog.on_find(True)),
                ("Format", None, _("Fo_rmat"))
            ]] +
            BothAction("Bold", "gtk-bold", _("_Bold"), "<control>B", _("Bold"),
                       lambda w: self._on_mod("bold"), "bold.png") +
            BothAction("Italic", "gtk-italic", _("_Italic"), "<control>I", _("Italic"),
                       lambda w: self._on_mod("italic"), "italic.png") +
            BothAction("Underline", "gtk-underline", _("_Underline"), "<control>U", _("Underline"),
                       lambda w: self._on_mod("underline"), "underline.png") +
            BothAction("Strike", None, _("S_trike"), "", _("Strike"),
                       lambda w: self._on_mod("strike"), "strike.png") +
            BothAction("Monospace", None, _("_Monospace"), "<control>M", _("Monospace"),
                       lambda w: self._on_mod("tt"), "fixed-width.png") +
            BothAction("Link", None, _("Lin_k"), "<control>L", _("Make Link"),
                       lambda w: self._on_toggle_link(), "link.png") +
            BothAction("No Wrapping", None, _("No _Wrapping"), "", _("No Wrapping"),
                       lambda w: self._on_mod("nowrap"), "no-wrap.png") +
            BothAction("Left Align", None, _("_Left Align"), "<shift><control>L", _("Left Align"),
                       lambda w: self._on_justify("left"), "alignleft.png") +
            BothAction("Center Align", None, _("C_enter Align"), "<shift><control>E", _("Center Align"),
                       lambda w: self._on_justify("center"), "aligncenter.png") +
            BothAction("Right Align", None, _("_Right Align"), "<shift><control>R", _("Right Align"),
                       lambda w: self._on_justify("right"), "alignright.png") +
            BothAction("Justify Align", None, _("_Justify Align"), "<shift><control>J", _("Justify Align"),
                       lambda w: self._on_justify("fill"), "alignjustify.png") +
            BothAction("Bullet List", None, _("_Bullet List"), "<control>asterisk", _("Bullet List"),
                       lambda w: self._on_bullet_list(), "bullet.png") +
            [Action(*x) for x in [
                ("Font Selector Tool", None, "", "", _("Set Font Face")),
                ("Font Size Tool", None, "", "", _("Set Font Size")),
                ("Font Fg Color Tool", None, "", "", _("Set Text Color")),
                ("Font Bg Color Tool", None, "", "", _("Set Background Color")),
                ("Indent More", None, _("Indent M_ore"), "<control>parenright", None,
                 lambda w: self._on_indent(), "indent-more.png"),
                ("Indent Less", None, _("Indent Le_ss"), "<control>parenleft", None,
                 lambda w: self._on_unindent(), "indent-less.png"),
                ("Increase Font Size", None, _("Increase Font _Size"), "<control>equal", None,
                 lambda w: self._on_font_size_inc()),
                ("Decrease Font Size", None, _("_Decrease Font Size"), "<control>minus", None,
                 lambda w: self._on_font_size_dec()),
                ("Apply Text Color", None, _("_Apply Text Color"), "", None,
                 lambda w: self._on_color_set("fg", self.fg_color_button), "font-inc.png"),
                ("Apply Background Color", None, _("A_pply Background Color"), "", None,
                 lambda w: self._on_color_set("bg", self.bg_color_button), "font-dec.png"),
                ("Choose Font", None, _("Choose _Font"), "<control><shift>F", None,
                 lambda w: self._on_choose_font(), "font.png"),
                ("Go to Link", None, _("Go to Lin_k"), "<control>space", None,
                 lambda w: self._editor.get_textview().click_iter()),
            ]] +
            [ToggleAction("Spell Check", None, _("_Spell Check"), "", None, self.on_spell_check_toggle)]
        )

    def get_ui(self):
        use_minitoolbar = self._app.pref.get("look_and_feel", "use_minitoolbar", default=False)

        ui = ["""
        <ui>
        <menubar name="main_menu_bar">
          <menu action="Edit">
            <placeholder name="Viewer">
              <placeholder name="Editor">
                <menuitem action="Insert Horizontal Rule"/>
                <menuitem action="Insert Image"/>
                <menuitem action="Insert New Image"/>
                <menuitem action="Insert Screenshot"/>
                <placeholder name="Extension"/>
              </placeholder>
            </placeholder>
          </menu>
          <menu action="Search">
            <placeholder name="Viewer">
              <placeholder name="Editor">
                <menuitem action="Find In Page"/>
                <menuitem action="Find Next In Page"/>
                <menuitem action="Find Previous In Page"/>
                <menuitem action="Replace In Page"/>
              </placeholder>
            </placeholder>
          </menu>
          <placeholder name Ascendantly
            <placeholder name="Viewer">
              <placeholder name="Editor">
                <menu action="Format">
                  <menuitem action="Bold"/>
                  <menuitem action="Italic"/>
                  <menuitem action="Underline"/>
                  <menuitem action="Strike"/>
                  <menuitem action="Monospace"/>
                  <menuitem action="Link"/>
                  <menuitem action="No Wrapping"/>
                  <separator/>
                  <menuitem action="Left Align"/>
                  <menuitem action="Center Align"/>
                  <menuitem action="Right Align"/>
                  <menuitem action="Justify Align"/>
                  <menuitem action="Bullet List"/>
                  <menuitem action="Indent More"/>
                  <menuitem action="Indent Less"/>
                  <separator/>
                  <menuitem action="Increase Font Size"/>
                  <menuitem action="Decrease Font Size"/>
                  <menuitem action="Apply Text Color"/>
                  <menuitem action="Apply Background Color"/>
                  <menuitem action="Choose Font"/>
                </menu>
              </placeholder>
            </placeholder>
          </menu>
          <menu action="Go">
            <placeholder name="Viewer">
              <placeholder name="Editor">
                <menuitem action="Go to Link"/>
              </placeholder>
            </placeholder>
          </menu>
          <menu action="Tools">
            <placeholder name="Viewer">
              <menuitem action="Spell Check"/>
            </placeholder>
          </menu>
        </menubar>
        </ui>
        """]

        if use_minitoolbar:
            ui.append("""
        <ui>
        <toolbar name="main_tool_bar">
          <placeholder name="Viewer">
            <placeholder name="Editor">
              <toolitem action="Bold Tool"/>
              <toolitem action="Italic Tool"/>
              <toolitem action="Underline Tool"/>
              <toolitem action="Link Tool"/>
              <toolitem action="Font Selector Tool"/>
              <toolitem action="Font Size Tool"/>
              <toolitem action="Font Fg Color Tool"/>
              <toolitem action="Font Bg Color Tool"/>
              <separator/>
              <toolitem action="Bullet List Tool"/>
            </placeholder>
          </placeholder>
        </toolbar>
        </ui>
        """)
        else:
            ui.append("""
        <ui>
        <toolbar name="main_tool_bar">
          <placeholder name="Viewer">
            <placeholder name="Editor">
              <toolitem action="Bold Tool"/>
              <toolitem action="Italic Tool"/>
              <toolitem action="Underline Tool"/>
              <toolitem action="Strike Tool"/>
              <toolitem action="Monospace Tool"/>
              <toolitem action="Link Tool"/>
              <toolitem action="No Wrapping Tool"/>
              <toolitem action="Font Selector Tool"/>
              <toolitem action="Font Size Tool"/>
              <toolitem action="Font Fg Color Tool"/>
              <toolitem action="Font Bg Color Tool"/>
              <separator/>
              <toolitem action="Left Align Tool"/>
              <toolitem action="Center Align Tool"/>
              <toolitem action="Right Align Tool"/>
              <toolitem action="Justify Align Tool"/>
              <toolitem action="Bullet List Tool"/>
              <separator/>
            </placeholder>
          </placeholder>
        </toolbar>
        </ui>
        """)

        return ui

    def setup_font_toggle(self, uimanager, path, stock=False, update_func=lambda ui, font: None):
        # Note: This method needs to be reimplemented for GTK 4 due to the removal of Gtk.UIManager
        print("Warning: setup_font_toggle needs to be reimplemented for GTK 4")
        return None

    def setup_menu(self, window, uimanager):
        # Note: This method needs to be reimplemented for GTK 4 due to the removal of Gtk.UIManager
        print("Warning: setup_menu needs to be reimplemented for GTK 4")
        pass

class ComboToolItem(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.set_margin_top(3)
        self.set_margin_bottom(3)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.combobox = Gtk.ComboBoxText.new_with_entry()
        for text in ['a', 'b', 'c', 'd', 'e', 'f']:
            self.combobox.append_text(text)
        self.append(self.combobox)

    def set_tooltip(self, tooltips, tip_text=None, tip_private=None):
        self.set_tooltip_text(tip_text)
        self.combobox.set_tooltip_text(tip_text)


class ComboToolAction(Action):
    def __init__(self, name, label, tooltip, stock_id):
        super().__init__(name=name, label=label, tooltip=tooltip, stock_id=stock_id)

    def create_tool_item(self):
        return ComboToolItem()