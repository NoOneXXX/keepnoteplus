# Python imports
import os
import shutil
import sys
import uuid

# PyGObject imports
from gi import require_version
require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib,  Gio
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# KeepNote imports
import keepnote
from keepnote import \
    KeepNoteError, \
    ensure_unicode, \
    FS_ENCODING
from keepnote.util.platform import unicode_gtk
from keepnote.notebook import \
    NoteBookError
from keepnote import notebook as notebooklib
from keepnote import tasklib
from keepnote.gui import \
    get_resource_pixbuf, \
    Action, \
    add_actions, \
    FileChooserDialog, \
    init_key_shortcuts, \
    UIManager
from keepnote.gui import \
    dialog_drag_drop_test, \
    dialog_wait
from keepnote.gui.tabbed_viewer import TabbedViewer

_ = keepnote.translate

# Constants
DEFAULT_WINDOW_SIZE = (1024, 600)
DEFAULT_WINDOW_POS = (-1, -1)

class KeepNoteWindow(Gtk.Window):
    """Main window for KeepNote"""

    def __init__(self, app, winid=None):
        super().__init__()

        self._app = app  # application object
        self._winid = winid if winid else str(uuid.uuid4())
        self._viewers = []

        # Window state
        self._maximized = False
        self._was_maximized = False
        self._iconified = False
        self._tray_icon = None
        self._recent_notebooks = []


        # Use Gtk ShortcutController for shortcuts in GTK 4
        self._shortcut_controller = Gtk.ShortcutController()
        self.add_controller(self._shortcut_controller)

        self.init_shortcuts()  # Replace init_key_shortcuts
        self.init_layout()
        self.setup_systray()

        # Load preferences for the first time
        self.load_preferences(True)

    def get_id(self):
        return self._winid

    def init_shortcuts(self):
        """Initialize keyboard shortcuts for GTK 4"""
        shortcuts = [
            ("<Control>O", self.on_open_notebook),
            ("<Control>S", lambda: self._app.save()),
            ("<Control>Q", self.on_quit),
            ("<Control>Z", self.on_undo),
            ("<Control><Shift>Z", self.on_redo),
            ("<Control>X", self.on_cut),
            ("<Control>C", self.on_copy),
            ("<Control><Shift>C", self.on_copy_tree),
            ("<Control>V", self.on_paste),
            ("<Control>K", lambda: self.search_box.grab_focus() if hasattr(self, 'search_box') else None),
        ]

        for trigger, callback in shortcuts:
            shortcut = Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string(trigger),
                Gtk.CallbackAction.new(callback)
            )
            self._shortcut_controller.add_shortcut(shortcut)

    def init_layout(self):
        # Init main window
        self.set_title(keepnote.PROGRAM_NAME)
        self.set_default_size(*DEFAULT_WINDOW_SIZE)
        self.set_icon_name("keepnote.py")

        # Main window signals
        # self.connect("error", lambda w, m, e, t: self.error(m, e, t))
        self.connect("close-request", self._on_close)
        self.connect("notify::maximized", self._on_window_state)
        # self.connect("size-allocate", self._on_window_size) // 原始的gtk3的写法 下面是gtk4的写法下面两行就是替换这行的
        self.connect("notify::default-width", self._on_window_size)
        self.connect("notify::default-height", self._on_window_size)

        # Dialogs
        self.drag_test = dialog_drag_drop_test.DragDropTestDialog(self)
        self.viewer = self.new_viewer()

        # Layout
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(main_vbox)

        # Menu bar
        main_vbox.set_margin_start(0)
        main_vbox.set_margin_end(0)
        main_vbox.set_margin_top(0)
        main_vbox.set_margin_bottom(0)
        self.menubar = self.make_menubar()
        main_vbox.append(self.menubar)

        # Toolbar
        main_vbox.append(self.make_toolbar())

        main_vbox2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_vbox2.set_margin_start(1)
        main_vbox2.set_margin_end(1)
        main_vbox2.set_margin_top(1)
        main_vbox2.set_margin_bottom(1)
        main_vbox.append(main_vbox2)

        # Viewer
        self.viewer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_vbox2.append(self.viewer_box)

        # Status bar
        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_vbox.append(status_hbox)

        self.status_bar = Gtk.Statusbar()
        status_hbox.append(self.status_bar)
        self.status_bar.set_size_request(300, -1)

        self.stats_bar = Gtk.Statusbar()
        status_hbox.append(self.stats_bar)

        # Viewer
        self.viewer_box.append(self.viewer)
        self.viewer.add_ui(self)

    def setup_systray(self):
        """Setup system tray for window"""
        print("Warning: System tray (Gtk.StatusIcon) is not supported in GTK 4. This feature is disabled.")
        self._tray_icon = None

    def _on_systray_popup_menu(self, status, button, time):
        pass  # System tray not supported in GTK 4

    # Viewers
    def new_viewer(self):
        viewer = TabbedViewer(self._app, self)
        viewer.connect("error", lambda w, m, e: self.error(m, e, None))
        viewer.connect("status", lambda w, m, b: self.set_status(m, b))
        viewer.connect("window-request", self._on_window_request)
        viewer.connect("current-node", self._on_current_node)
        viewer.connect("modified", self._on_viewer_modified)
        return viewer

    def add_viewer(self, viewer):
        self._viewers.append(viewer)

    def remove_viewer(self, viewer):
        self._viewers.remove(viewer)

    def get_all_viewers(self):
        return self._viewers

    def get_all_notebooks(self):
        return set([n for n in (v.get_notebook() for v in self._viewers) if n is not None])

    # Accessors
    def get_app(self):
        return self._app

    def get_viewer(self):
        return self.viewer

    def get_notebook(self):
        return self.viewer.get_notebook()

    def get_current_node(self):
        return self.viewer.get_current_node()

    # Main window GUI callbacks
    def _on_window_state(self, obj, param):
        surface = self.get_surface()
        if surface is not None:
            state = surface.get_state()
            self._maximized = bool(state & Gdk.ToplevelState.MAXIMIZED)
            self._fullscreen = bool(state & Gdk.ToplevelState.FULLSCREEN)
        else:
            self._maximized = False
            self._fullscreen = False

    def _on_window_size(self, window, allocation):
        if not self._maximized and not self._iconified:
            self._app.pref.get("window")["window_size"] = (allocation.width, allocation.height)

    def _on_tray_icon_activate(self, icon):
        pass  # System tray not supported in GTK 4

    # Viewer callbacks
    def _on_window_request(self, viewer, action):
        if action == "minimize":
            self.minimize_window()
        elif action == "restore":
            self.restore_window()
        else:
            raise Exception("unknown window request: " + str(action))

    # Window manipulation
    def minimize_window(self):
        if self._iconified:
            return
        self.minimize()
        self._iconified = True

    def restore_window(self):
        self.unminimize()
        self.present()
        self._iconified = False

    def on_new_window(self):
        win = self._app.new_window()
        notebook = self.get_notebook()
        if notebook:
            self._app.ref_notebook(notebook)
            win.set_notebook(notebook)

    # Application preferences
    def load_preferences(self, first_open=False):
        p = self._app.pref
        # window_size = p.get("window", "window_size", default=DEFAULT_WINDOW_SIZE)
        window_section = p.get("window", {})
        window_size = window_section.get("window_size", DEFAULT_WINDOW_SIZE)

        print(f"window_size: {window_size} (type: {type(window_size)})")
        if isinstance(window_size, str):
            try:
                width, height = map(int, window_size.replace(" ", "").split(","))
                window_size = (width, height)
            except (ValueError, TypeError) as e:
                print(f"Error parsing window_size '{window_size}': {e}. Using default.")
                window_size = DEFAULT_WINDOW_SIZE
        if not isinstance(window_size, (tuple, list)) or len(window_size) != 2:
            window_size = DEFAULT_WINDOW_SIZE
        print(f"Parsed window_size: {window_size}")

        window_section2 = p.get("window", {})
        window_maximized = window_section2.get("window_maximized", True)

        self.setup_systray()

        window_section3 = p.get("window", {})
        use_systray = window_section3.get("use_systray", True)
        if first_open:
            self.set_default_size(*window_size)
            if window_maximized:
                self.maximize()
            window_section4 = p.get("window", {})
            if use_systray and window_section4.get("minimize_on_start", False):
                self.minimize()

        # GTK 4 中不再支持隐藏标题栏，下面的调用被移除
        # window_section5 = p.get("window", {})
        # skip = window_section5.get("skip_taskbar", False)
        # if use_systray:
        #     self.set_hide_titlebar_when_maximized(skip)
        # 可选日志说明
        print("GTK 4: set_hide_titlebar_when_maximized is no longer supported. Ignoring skip_taskbar setting.")
        # self.set_keep_above(keep_above)
        print("GTK 4: 'set_keep_above' is no longer supported. Ignoring 'keep_above' setting.")
        # window_section6 = p.get("window", {})
        # keep_above = window_section6.get("keep_above", False)
        # self.set_keep_above(keep_above)
        # window_section7 = p.get("window", {})
        # if window_section7.get("stick", False):
        #     self.stick()
        # else:
        #     self.unstick()

        # Load recent notebooks

        self._recent_notebooks = p.get("recent_notebooks", [])
        if first_open and not self._recent_notebooks:
            default_path = os.path.join(keepnote.get_user_pref_dir(), "DefaultNotebook")
            if not os.path.exists(default_path):
                self.new_notebook(default_path)
            self._recent_notebooks = [default_path]
        self.set_recent_notebooks_menu(self._recent_notebooks)

        # Ensure a notebook is opened
        if self._recent_notebooks and not self.get_notebook():
            self.open_notebook(self._recent_notebooks[0])

        self.viewer.load_preferences(self._app.pref, first_open)

    def save_preferences(self):
        p = self._app.pref
        p.set("window", "window_maximized", self._maximized)
        p.set("recent_notebooks", self._recent_notebooks)
        self.viewer.save_preferences(self._app.pref)

    def set_recent_notebooks_menu(self, recent_list):
        """
        Populate the recent notebooks section inside the File menu dynamically.
        """
        if not hasattr(self, 'file_menu_model'):
            return  # file_menu_model not ready yet
        # Remove previous section
        if hasattr(self, 'recent_section_index'):
            try:
                self.file_menu_model.remove(self.recent_section_index)
            except Exception:
                pass

        # Create new menu section
        recent_menu = Gio.Menu()
        for i, path in enumerate(recent_list):
            action_name = f"open_recent_{i}"
            label = os.path.basename(path)
            recent_menu.append(label, f"win.{action_name}")

            if not self.win_actions.has_action(action_name):
                action = Gio.SimpleAction.new(action_name, None)
                action.connect("activate", lambda a, p, pth=path: self.on_open_notebook_file(pth))
                self.win_actions.add_action(action)

        self.file_menu_model.insert_section(1, "Recent Notebooks", recent_menu)
        self.recent_section_index = 1

    def open_notebook_file(self, path):
        """
        Open a notebook by file path — called by recent menu actions.
        Returns the notebook object, or None on failure.
        """
        try:
            from keepnote.notebook import NoteBook
            notebook = NoteBook()
            notebook.load(path)
            self.notebook = notebook  # 或写成 self.attach_notebook(notebook)
            if notebook.index_needed():
                self.update_index(notebook)
            return notebook
        except Exception as e:
            print(f"[ERROR] Failed to open notebook at {path}: {e}")
            return None

    def add_recent_notebook(self, filename):
        if filename in self._recent_notebooks:
            self._recent_notebooks.remove(filename)
        self._recent_notebooks = [filename] + self._recent_notebooks[:keepnote.gui.MAX_RECENT_NOTEBOOKS]
        self.set_recent_notebooks_menu(self._recent_notebooks)

    # Notebook open/save/close UI
    def on_new_notebook(self):
        print("========start new notebook thread========")
        dialog = Gtk.FileChooserDialog(
            title=_("New Notebook"),
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(_("Cancel"), Gtk.ResponseType.CANCEL,
                     _("New"), Gtk.ResponseType.OK)
        )

        response = dialog.run()
        if response == Gtk.ResponseType.OK and dialog.get_filename():
            filename = unicode_gtk(dialog.get_filename())
            self.new_notebook(filename)

        dialog.destroy()

    def on_open_notebook(self):
        dialog = Gtk.FileChooserDialog(
            title=_("Open Notebook"), parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(_("Cancel"), Gtk.ResponseType.CANCEL,
                     _("Open"), Gtk.ResponseType.OK))

        content_area = dialog.get_content_area()
        content_area.set_margin_start(5)
        content_area.set_margin_end(5)
        content_area.set_margin_top(5)
        content_area.set_margin_bottom(5)

        def on_folder_changed(filechooser):
            folder = unicode_gtk(filechooser.get_current_folder_file().get_path())
            if os.path.exists(os.path.join(folder, notebooklib.PREF_FILE)):
                filechooser.response(Gtk.ResponseType.OK)

        dialog.connect("current-folder-changed", on_folder_changed)

        path = self._app.get_default_path("new_notebook_path")
        if os.path.exists(path):
            dialog.set_current_folder_file(Gio.File.new_for_path(path))

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*")
        file_filter.set_name(_("All files (*.*)"))
        dialog.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*.nbk")
        file_filter.set_name(_("Notebook (*.nbk)"))
        dialog.add_filter(file_filter)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            path = ensure_unicode(dialog.get_current_folder_file().get_path(), FS_ENCODING)
            if path:
                self._app.pref.set("default_paths", "new_notebook_path", os.path.dirname(path))
            notebook_file = ensure_unicode(dialog.get_file().get_path(), FS_ENCODING)
            if notebook_file:
                self.open_notebook(notebook_file)

        dialog.destroy()

    def on_open_notebook_url(self):
        dialog = Gtk.Dialog(
            title="Open Notebook from URL",
            parent=self,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        )

        p = dialog.get_content_area()
        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        p.append(h)

        l = Gtk.Label(label="URL: ")
        h.append(l)

        entry = Gtk.Entry()
        entry.set_width_chars(80)
        entry.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))
        h.append(entry)

        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Open", Gtk.ResponseType.OK)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            url = unicode_gtk(entry.get_text())
            if url:
                self.open_notebook(url)

        dialog.destroy()

    def _on_close(self):
        try:
            self._app.save()
            self.close_notebook()
            if self._tray_icon:
                pass  # System tray not supported in GTK 4
        except Exception as e:
            self.error("Error while closing", e, sys.exc_info()[2])
        return False

    def close(self):
        self._on_close()
        self.close()

    def on_quit(self):
        self._app.save()
        self._app.quit()

    # Notebook actions
    def save_notebook(self, silent=False):
        try:
            for notebook in self.get_all_notebooks():
                p = notebook.pref.get("windows", "ids", define=True)
                p[self._winid] = {
                    "viewer_type": self.viewer.get_name(),
                    "viewerid": self.viewer.get_id()}
            self.viewer.save()
            self.set_status(_("Notebook saved"))
        except Exception as e:
            if not silent:
                self.error(_("Could not save notebook."), e, sys.exc_info()[2])
                self.set_status(_("Error saving notebook"))

    def reload_notebook(self):
        notebook = self.viewer.get_notebook()
        if notebook is None:
            self.error(_("Reloading only works when a notebook is open."))
            return
        filename = notebook.get_filename()
        self._app.close_all_notebook(notebook, False)
        self.open_notebook(filename)
        self.set_status(_("Notebook reloaded"))

    def new_notebook(self, filename):
        if self.viewer.get_notebook() is not None:
            self.close_notebook()

        try:
            filename = ensure_unicode(filename, FS_ENCODING)
            filename = os.path.normpath(filename)
            print(f"Creating notebook at: {filename}")

            parent_dir = os.path.dirname(filename)
            if not parent_dir:
                parent_dir = os.getcwd()
            if not os.path.exists(parent_dir):
                raise NoteBookError(f"Parent directory does not exist: '{parent_dir}'")
            if not os.access(parent_dir, os.W_OK):
                raise NoteBookError(f"No write permission for directory: '{parent_dir}'")

            if os.path.exists(filename):
                raise NoteBookError(f"Path already exists: '{filename}'")

            notebook = notebooklib.NoteBook()
            notebook.create(filename)
            notebook.set_attr("title", os.path.basename(filename))
            notebook.close()
            self.set_status(_("Created '%s'") % notebook.get_title())
        except NoteBookError as e:
            error_msg = f"Could not create new notebook at '{filename}': {str(e)}"
            self.error(error_msg, e, sys.exc_info()[2])
            self.set_status("")
            return None

        return self.open_notebook(filename, new=True)

    def _load_notebook(self, filename):
        notebook = self.open_notebook_file(filename)
        if notebook is None:
            return None
        if notebook.index_needed():
            self.update_index(notebook)
        return notebook


    def _restore_windows(self, notebook, open_here=True):
        win_lookup = dict((w.get_id(), w) for w in self._app.get_windows())

        def open_in_window(winid, viewerid, notebook):
            win = win_lookup.get(winid)
            if win is None:
                win = self._app.new_window()
                win_lookup[winid] = win
                win._winid = winid
                if viewerid:
                    win.get_viewer().set_id(viewerid)
            self._app.ref_notebook(notebook)
            win.set_notebook(notebook)

        windows = notebook.pref.get("windows", "ids", define=True)
        notebook.pref.get("viewers", "ids", define=True)

        if len(windows) == 0:
            self.set_notebook(notebook)
        elif len(windows) == 1:
            winid, winpref = list(windows.items())[0]
            viewerid = winpref.get("viewerid")
            if viewerid is not None:
                if not self.get_all_notebooks():
                    self._winid = winid
                    self.viewer.set_id(viewerid)
                    self.set_notebook(notebook)
                elif open_here:
                    notebook.pref.set("windows", "ids", {self._winid: {"viewerid": self.viewer.get_id(), "viewer_type": self.viewer.get_name()}})
                    notebook.pref.set("viewers", "ids", self.viewer.get_id(), notebook.pref.get("viewers", "ids", viewerid, define=True))
                    del notebook.pref.get("viewers", "ids")[viewerid]
                    self.set_notebook(notebook)
                else:
                    open_in_window(winid, viewerid, notebook)
                    self._app.unref_notebook(notebook)
        elif len(windows) > 1:
            restoring_ids = set(windows.keys())
            if not self.get_all_notebooks():
                if self._winid not in restoring_ids:
                    self._winid = next(iter(restoring_ids))
                restoring_ids.remove(self._winid)
                viewerid = windows[self._winid].get("viewerid")
                if viewerid:
                    self.viewer.set_id(viewerid)
                self.set_notebook(notebook)
            while restoring_ids:
                winid = restoring_ids.pop()
                viewerid = windows[winid].get("viewerid")
                open_in_window(winid, viewerid, notebook)
            self._app.unref_notebook(notebook)

    def open_notebook(self, filename, new=False, open_here=True):
        notebook = self._load_notebook(filename)
        if notebook is None:
            return
        self._restore_windows(notebook, open_here=open_here)
        if not new:
            self.set_status(_("Loaded '%s'") % notebook.get_title())
        self.update_title()
        self.add_recent_notebook(filename)
        return notebook

    def close_notebook(self, notebook=None):
        if notebook is None:
            notebook = self.get_notebook()
        self.viewer.close_notebook(notebook)
        self.set_status(_("Notebook closed"))

    def set_notebook(self, notebook):
        self.viewer.set_notebook(notebook)

    def update_index(self, notebook=None, clear=False):
        if notebook is None:
            notebook = self.viewer.get_notebook()
        if notebook is None:
            return

        def update(task):
            if clear:
                notebook.clear_index()
            try:
                for node in notebook.index_all():
                    if task.aborted():
                        break
            except Exception as e:
                self.error(_("Error during index"), e, sys.exc_info()[2])
            task.finish()

        self.wait_dialog(_("Indexing notebook"), _("Indexing..."), tasklib.Task(update))

    def compact_index(self, notebook=None):
        if notebook is None:
            notebook = self.viewer.get_notebook()
        if notebook is None:
            return

        def update(task):
            notebook.index("compact")

        self.wait_dialog(_("Compacting notebook index"), _("Compacting..."), tasklib.Task(update))

    # Viewer callbacks
    def update_title(self, node=None):
        notebook = self.viewer.get_notebook()
        if notebook is None:
            self.set_title(keepnote.PROGRAM_NAME)
        else:
            title = notebook.get_attr("title", "")
            if node is None:
                node = self.get_current_node()
            if node is not None:
                title += ": " + node.get_attr("title", "")
            modified = notebook.save_needed()
            self.set_title(f"* {title}" if modified else title)
            if modified:
                self.set_status(_("Notebook modified"))

    def _on_current_node(self, viewer, node):
        self.update_title(node)

    def _on_viewer_modified(self, viewer, modified):
        self.update_title()

    # Page and folder actions
    def get_selected_nodes(self):
        return self.viewer.get_selected_nodes()

    def confirm_delete_nodes(self, nodes):
        for node in nodes:
            if node.get_attr("content_type") == notebooklib.CONTENT_TYPE_TRASH:
                self.error(_("The Trash folder cannot be deleted."), None)
                return False
            if node.get_parent() is None:
                self.error(_("The top-level folder cannot be deleted."), None)
                return False

        message = _("Do you want to delete this note and all of its children?") if len(nodes) > 1 or len(nodes[0].get_children()) > 0 else _("Do you want to delete this note?")
        return self._app.ask_yes_no(message, _("Delete Note"), parent=self.get_toplevel())

    def on_empty_trash(self):
        if self.get_notebook() is None:
            return
        try:
            self.get_notebook().empty_trash()
        except NoteBookError as e:
            self.error(_("Could not empty trash."), e, sys.exc_info()[2])

    # Action callbacks
    def on_view_node_external_app(self, app, node=None, kind=None):
        self._app.save()
        if node is None:
            nodes = self.get_selected_nodes()
            if not nodes:
                self.emit("error", _("No notes are selected."), None, None)
                return
            node = nodes[0]
        try:
            self._app.run_external_app_node(app, node, kind)
        except KeepNoteError as e:
            self.emit("error", e.msg, e, sys.exc_info()[2])

    # Cut/copy/paste
    def on_cut(self):
        widget = self.get_focus()
        if widget and hasattr(widget, "cut_clipboard"):
            widget.cut_clipboard()

    def on_copy(self):
        widget = self.get_focus()
        if widget and hasattr(widget, "copy_clipboard"):
            widget.copy_clipboard()

    def on_copy_tree(self):
        widget = self.get_focus()
        if widget and hasattr(widget, "copy_tree_clipboard"):
            widget.copy_tree_clipboard()

    def on_paste(self):
        widget = self.get_focus()
        if widget and hasattr(widget, "paste_clipboard"):
            widget.paste_clipboard()

    def on_undo(self):
        self.viewer.undo()

    def on_redo(self):
        self.viewer.redo()

    # Misc.
    def view_error_log(self):
        try:
            filename = os.path.realpath(keepnote.get_user_error_log())
            filename2 = filename + ".bak"
            shutil.copy(filename, filename2)
            self._app.run_external_app("text_editor", filename2)
        except Exception as e:
            self.error(_("Could not open error log") + ":\n" + str(e), e, sys.exc_info()[2])

    def view_config_files(self):
        try:
            filename = keepnote.get_user_pref_dir()
            self._app.run_external_app("file_explorer", filename)
        except Exception as e:
            self.error(_("Could not open error log") + ":\n" + str(e), e, sys.exc_info()[2])

    # Help/about dialog
    def on_about(self):
        def func(dialog, link, data):
            try:
                self._app.open_webpage(link)
            except KeepNoteError as e:
                self.error(e.msg, e, sys.exc_info()[2])

        about = Gtk.AboutDialog()
        about.set_program_name(keepnote.PROGRAM_NAME)
        about.set_version(keepnote.PROGRAM_VERSION_TEXT)
        about.set_copyright(keepnote.COPYRIGHT)
        about.set_logo(get_resource_pixbuf("keepnote.py-icon.png"))
        about.set_website(keepnote.WEBSITE)
        about.set_license_type(Gtk.License.GPL_2_0)
        about.set_translator_credits(keepnote.TRANSLATOR_CREDITS)

        license_file = keepnote.get_resource("rc", "COPYING")
        if os.path.exists(license_file):
            about.set_license(open(license_file).read())

        about.set_transient_for(self)
        about.connect("activate-link", func)
        about.connect("response", lambda d, r: d.destroy())
        about.present()

    # Messages, warnings, errors UI/dialogs
    def set_status(self, text, bar="status"):
        if bar == "status":
            self.status_bar.pop(0)
            self.status_bar.push(0, text)
        elif bar == "stats":
            self.stats_bar.pop(0)
            self.stats_bar.push(0, text)
        else:
            raise Exception(f"unknown bar '{bar}'")

    def error(self, text, error=None, tracebk=None):
        self._app.error(text, error, tracebk)

    def wait_dialog(self, title, text, task, cancel=True):
        self._app.pause_auto_save(True)
        dialog = dialog_wait.WaitDialog(self)
        dialog.show(title, text, task, cancel=cancel)
        self._app.pause_auto_save(False)

    # Menus
    def make_menubar(self):
        """
        Create a full-featured GTK 4-compatible menubar using Gtk.MenuButton and Gio.Menu.
        This replaces deprecated Gtk.MenuBar, Gtk.MenuItem, Gtk.Menu from GTK 3.
        """
        menubar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Create and insert action group for "win" domain
        self.win_actions = Gio.SimpleActionGroup()
        self.insert_action_group("win", self.win_actions)

        # === Helper to build menu button and action group ===
        def create_menu_button(title, actions):
            menu = Gio.Menu()
            for label, action_name, callback in actions:
                menu.append(label, f"win.{action_name}")

                if not self.win_actions.has_action(action_name):
                    action = Gio.SimpleAction.new(action_name, None)
                    action.connect("activate", lambda a, p, cb=callback: cb())
                    self.win_actions.add_action(action)

            btn = Gtk.MenuButton(label=title)
            btn.set_popover(Gtk.PopoverMenu.new_from_model(menu))
            return btn

        # === File Menu ===
        file_actions = [
            ("New Notebook", "new_notebook", self.on_new_notebook),
            ("Open Notebook", "open_notebook", self.on_open_notebook),
            ("Save Notebook", "save_notebook", lambda: self.save_notebook(silent=False)),
            ("Close Notebook", "close_notebook", lambda: self._app.close_all_notebook(self.get_notebook())),
            ("Reload Notebook", "reload_notebook", self.reload_notebook),
            ("Empty Trash", "empty_trash", self.on_empty_trash),
            ("Quit", "quit", self.on_quit),
        ]
        menubar_box.append(create_menu_button("File", file_actions))

        # === Edit Menu ===
        edit_actions = [
            ("Undo", "undo", self.on_undo),
            ("Redo", "redo", self.on_redo),
            ("Cut", "cut", self.on_cut),
            ("Copy", "copy", self.on_copy),
            ("Copy Tree", "copy_tree", self.on_copy_tree),
            ("Paste", "paste", self.on_paste),
        ]
        menubar_box.append(create_menu_button("Edit", edit_actions))

        # === Search Menu ===
        search_actions = [
            ("Search All Notes", "search_all",
             lambda: self.search_box.grab_focus() if hasattr(self, 'search_box') else None),
        ]
        menubar_box.append(create_menu_button("Search", search_actions))

        # === Tools Menu ===
        tools_actions = [
            ("Update Notebook Index", "update_index", lambda: self.update_index(clear=True)),
            ("Compact Notebook Index", "compact_index", self.compact_index),
            ("Open Notebook from URL", "open_url", self.on_open_notebook_url),
        ]
        menubar_box.append(create_menu_button("Tools", tools_actions))

        # === Window Menu ===
        window_actions = [
            ("New Window", "new_window", self.on_new_window),
            ("Close Window", "close_window", self.close),
        ]
        menubar_box.append(create_menu_button("Window", window_actions))

        # === Help Menu ===
        help_actions = [
            ("View Error Log", "error_log", self.view_error_log),
            ("View Preference Files", "pref_files", self.view_config_files),
            ("Drag and Drop Test", "drag_drop_test", lambda: self.drag_test.on_drag_and_drop_test()),
            ("About", "about", self.on_about),
        ]
        menubar_box.append(create_menu_button("Help", help_actions))

        return menubar_box

    def make_toolbar(self):
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_start(0)
        toolbar.set_margin_end(0)
        toolbar.set_margin_top(0)
        toolbar.set_margin_bottom(0)

        self.search_box = SearchBox(self)
        toolbar.append(self.search_box)

        search_button = Gtk.Button(label=_("Search"))
        search_button.connect("clicked", lambda w: self.search_box.on_search_nodes())
        toolbar.append(search_button)
        # Call recent menu setup here to ensure file_menu_model is initialized
        if hasattr(self, '_recent_notebooks'):
            self.set_recent_notebooks_menu(self._recent_notebooks)

        return toolbar



class SearchBox(Gtk.Entry):
    def __init__(self, window):
        super().__init__()

        self._window = window
        self.connect("changed", self._on_search_box_text_changed)
        self.connect("activate", lambda w: self.on_search_nodes())

        self.search_box_list = Gtk.ListStore.new([str, str])
        self.search_box_completion = Gtk.EntryCompletion()
        self.search_box_completion.connect("match-selected", self._on_search_box_completion_match)
        self.search_box_completion.set_match_func(lambda c, k, i: True, None)
        self.search_box_completion.set_model(self.search_box_list)
        self.search_box_completion.set_text_column(0)
        self.set_completion(self.search_box_completion)

    def on_search_nodes(self):
        if not self._window.get_notebook():
            return

        words = [x.lower() for x in unicode_gtk(self.get_text()).strip().split()]
        self._window.get_viewer().start_search_result()

        from threading import Lock
        from queue import Queue
        queue = Queue()
        lock = Lock()

        def search(task):
            alldone = Lock()
            alldone.acquire()

            def gui_update():
                lock.acquire()
                more = True
                try:
                    maxstep = 20
                    for _ in range(maxstep):
                        if task.aborted():
                            more = False
                            break
                        if queue.empty():
                            break
                        node = queue.get()
                        if node is None:
                            more = False
                            break
                        self._window.get_viewer().add_search_result(node)
                except Exception as e:
                    self._window.error(_("Unexpected error"), e)
                    more = False
                finally:
                    lock.release()
                if not more:
                    alldone.release()
                return more
            GLib.idle_add(gui_update)

            notebook = self._window.get_notebook()
            try:
                nodes = (notebook.get_node_by_id(nodeid) for nodeid in notebook.search_node_contents(" ".join(words)) if nodeid)
            except:
                keepnote.log_error()

            try:
                lock.acquire()
                for node in nodes:
                    if task.aborted():
                        break
                    lock.release()
                    if node:
                        queue.put(node)
                    lock.acquire()
                lock.release()
                queue.put(None)
            except Exception as e:
                self.error(_("Unexpected error"), e)

            if not task.aborted():
                alldone.acquire()

        task = tasklib.Task(search)
        self._window.wait_dialog(_("Searching notebook"), _("Searching..."), task)
        if task.exc_info()[0]:
            e, t, tr = task.exc_info()
            keepnote.log_error(e, tr)

        self._window.get_viewer().end_search_result()

    def focus_on_search_box(self):
        self.grab_focus()

    def _on_search_box_text_changed(self, entry):
        self.search_box_update_completion()

    def search_box_update_completion(self):
        if not self._window.get_notebook():
            return
        text = unicode_gtk(self.get_text())
        self.search_box_list.clear()
        if text:
            results = self._window.get_notebook().search_node_titles(text)[:10]
            for nodeid, title in results:
                self.search_box_list.append([title, nodeid])

    def _on_search_box_completion_match(self, completion, model, iter_):
        if not self._window.get_notebook():
            return
        nodeid = model[iter_][1]
        node = self._window.get_notebook().get_node_by_id(nodeid)
        if node:
            self._window.get_viewer().goto_node(node, False)