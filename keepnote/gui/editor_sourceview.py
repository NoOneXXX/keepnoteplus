# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk

# Try to import gtksourceview5 (for GTK 4)
try:
    gi.require_version('GtkSource', '5')  # Use version 5 for GTK 4 compatibility
    from gi.repository import GtkSource
    SourceView = GtkSource.View
    SourceBuffer = GtkSource.Buffer
    SourceLanguageManager = GtkSource.LanguageManager
except ImportError:
    SourceView = None
    SourceBuffer = None
    SourceLanguageManager = None

# KeepNote imports
import keepnote
from keepnote import KeepNoteError, unicode_gtk
from keepnote.notebook import NoteBookError, parse_node_url, is_node_url
from keepnote.gui.richtext import RichTextView, RichTextBuffer, RichTextIO, RichTextError
from keepnote.gui import CONTEXT_MENU_ACCEL_PATH, Action, ToggleAction, add_actions
from keepnote.gui.editor import KeepNoteEditor

_ = keepnote.translate

class TextEditor(KeepNoteEditor):
    """Text editor for KeepNote, supporting plain text and source code"""

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
        self._textview_io = RichTextIO()

        # Textview and its callbacks
        if SourceView:
            self._textview = SourceView.new_with_buffer(SourceBuffer())
            self._textview.get_buffer().set_highlight_syntax(True)
        else:
            self._textview = RichTextView(RichTextBuffer(self._app.get_richtext_tag_table()))
            self._textview.disable()
            self._textview.connect("modified", self._on_modified_callback)
            self._textview.connect("visit-url", self._on_visit_url)

        # Scrollbars
        self._sw = Gtk.ScrolledWindow()
        self._sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._sw.set_has_frame(True)  # Replaces set_shadow_type
        self._sw.set_child(self._textview)  # Changed from add to set_child
        self.append(self._sw)  # Changed from pack_start to append

        # Menus and find dialog are commented out in the original code
        # self.editor_menus = EditorMenus(self._app, self)
        # self.find_dialog = dialog_find.KeepNoteFindDialog(self)

    def set_notebook(self, notebook):
        """Set notebook for editor"""
        self._notebook = notebook
        if not self._notebook:
            self.clear_view()

    def load_preferences(self, app_pref, first_open=False):
        """Load application preferences"""
        if not SourceView:
            self._textview.set_default_font("Monospace 10")

    def save_preferences(self, app_pref):
        """Save application preferences"""
        pass

    def get_textview(self):
        """Return the textview"""
        return self._textview

    def is_focus(self):
        """Return True if text editor has focus"""
        return self._textview.has_focus()

    def grab_focus(self):
        """Pass focus to textview"""
        self._textview.grab_focus()

    def clear_view(self):
        """Clear editor view"""
        self._page = None
        if not SourceView:
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

        if not nodes:
            self.clear_view()
        else:
            page = nodes[0]
            self._page = page
            if not SourceView:
                self._textview.enable()

            try:
                if page.has_attr("payload_filename"):
                    infile = page.open_file(page.get_attr("payload_filename"), "r", "utf-8")
                    text = infile.read()
                    infile.close()
                    self._textview.get_buffer().set_text(text)
                    self._load_cursor()

                    if SourceView:
                        manager = SourceLanguageManager.get_default()
                        lang = manager.get_language("python")
                        if lang:
                            self._textview.get_buffer().set_language(lang)

                else:
                    self.clear_view()

            except RichTextError as e:
                self.clear_view()
                self.emit("error", e.msg, e)
            except Exception as e:
                self.clear_view()
                self.emit("error", "Unknown error", e)

        if nodes:
            self.emit("view-node", nodes[0])

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
        if (self._page is not None and
                self._page.is_valid() and
                (SourceView or self._textview.is_modified())):
            try:
                buf = self._textview.get_buffer()
                text = unicode_gtk(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False))
                out = self._page.open_file(self._page.get_attr("payload_filename"), "w", "utf-8")
                out.write(text)
                out.close()

                self._page.set_attr_timestamp("modified_time")
                self._page.save()

            except (RichTextError, NoteBookError, Exception) as e:
                self.emit("error", str(e), e)

    def save_needed(self):
        """Returns True if textview is modified"""
        if not SourceView:
            return self._textview.is_modified()
        return False

    def add_ui(self, window):
        if not SourceView:
            self._textview.set_accel_group(window.get_accel_group())
            self._textview.set_accel_path(CONTEXT_MENU_ACCEL_PATH)

    def remove_ui(self, window):
        pass

    # Callbacks for textview
    def _on_modified_callback(self, textview, modified):
        self.emit("modified", self._page, modified)
        if modified:
            self._page.mark_modified()
            self._page.notify_change(False)

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

class EditorMenus:
    """Menus for the TextEditor"""

    def __init__(self, app, editor):
        self._app = app
        self._editor = editor
        self._action_group = None
        self._uis = []
        self.spell_check_toggle = None
        self._removed_widgets = []

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
                ("Find In Page", "gtk-find", _("_Find In Page..."), "<control>F", None,
                 lambda w: self._editor.find_dialog.on_find(False)),
                ("Find Next In Page", "gtk-find", _("Find _Next In Page..."), "<control>G", None,
                 lambda w: self._editor.find_dialog.on_find(False, forward=True)),
                ("Find Previous In Page", "gtk-find", _("Find Pre_vious In Page..."), "<control><shift>G", None,
                 lambda w: self._editor.find_dialog.on_find(False, forward=False)),
                ("Replace In Page", "gtk-find-and-replace", _("_Replace In Page..."), "<control>R", None,
                 lambda w: self._editor.find_dialog.on_find(True)),
            ]] +
            [ToggleAction("Spell Check", None, _("_Spell Check"), "", None, self.on_spell_check_toggle)]
        )

    def get_ui(self):
        ui = ["""
        <ui>
        <menubar name="main_menu_bar">
          <menu action="Edit">
            <placeholder name="Viewer">
              <placeholder name="Editor">
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
          <placeholder name="Viewer">
            <placeholder name="Editor">
            </placeholder>
          </placeholder>
          <menu action="Go">
            <placeholder name="Viewer">
              <placeholder name="Editor">
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

        ui.append("""
        <ui>
        <toolbar name="main_tool_bar">
          <placeholder name="Viewer">
            <placeholder name="Editor">
            </placeholder>
          </placeholder>
        </toolbar>
        </ui>
        """)

        return ui

    def setup_menu(self, window, uimanager):
        # Note: This method needs to be reimplemented for GTK 4 due to the removal of Gtk.UIManager
        print("Warning: setup_menu needs to be reimplemented for GTK 4")
        pass