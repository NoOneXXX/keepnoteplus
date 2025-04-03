
# Python imports
import os
import shutil
import sys
import uuid

# PyGObject imports

from gi import require_version
require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GObject
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# KeepNote imports
import keepnote
from keepnote import \
    KeepNoteError, \
    ensure_unicode, \
    unicode_gtk, \
    FS_ENCODING
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
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        self._app = app  # application object
        self._winid = winid if winid else str(uuid.uuid4())
        self._viewers = []

        # Window state
        self._maximized = False
        self._was_maximized = False
        self._iconified = False
        self._tray_icon = None
        self._recent_notebooks = []

        self._uimanager = UIManager()
        self._accel_group = self._uimanager.get_accel_group()
        self.add_accel_group(self._accel_group)

        init_key_shortcuts()
        self.init_layout()
        self.setup_systray()

        # Load preferences for the first time
        self.load_preferences(True)

    def get_id(self):
        return self._winid

    def init_layout(self):
        # Init main window
        self.set_title(keepnote.PROGRAM_NAME)
        self.set_default_size(*DEFAULT_WINDOW_SIZE)
        self.set_icon_list([
            get_resource_pixbuf("keepnote-16x16.png"),
            get_resource_pixbuf("keepnote-32x32.png"),
            get_resource_pixbuf("keepnote-64x64.png")
        ])
        # ... other initialization code ...

        # Main window signals
        self.connect("error", lambda w, m, e, t: self.error(m, e, t))
        self.connect("delete-event", lambda w, e: self._on_close())
        self.connect("window-state-event", self._on_window_state)
        self.connect("size-allocate", self._on_window_size)

        # Dialogs
        self.drag_test = dialog_drag_drop_test.DragDropTestDialog(self)
        self.viewer = self.new_viewer()

        # Layout
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_vbox)

        # Menu bar
        main_vbox.set_border_width(0)
        self.menubar = self.make_menubar()
        main_vbox.pack_start(self.menubar, False, True, 0)

        # Toolbar
        main_vbox.pack_start(self.make_toolbar(), False, True, 0)

        main_vbox2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_vbox2.set_border_width(1)
        main_vbox.pack_start(main_vbox2, True, True, 0)

        # Viewer
        self.viewer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_vbox2.pack_start(self.viewer_box, True, True, 0)

        # Status bar
        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_vbox.pack_start(status_hbox, False, True, 0)

        # Status bar
        self.status_bar = Gtk.Statusbar()
        status_hbox.pack_start(self.status_bar, False, True, 0)
        # Remove: self.status_bar.set_has_resize_grip(False)
        self.status_bar.set_size_request(300, -1)

        # Set resize grip on the window (optional)
        self.set_has_resize_grip(False)  # Note: Deprecated in GTK 3.14+

        self.stats_bar = Gtk.Statusbar()
        status_hbox.pack_start(self.stats_bar, True, True, 0)

        # Viewer
        self.viewer_box.pack_start(self.viewer, True, True, 0)
        self.viewer.add_ui(self)

    def setup_systray(self):
        """Setup system tray for window"""
        if not self._tray_icon:
            self._tray_icon = Gtk.StatusIcon()
            self._tray_icon.set_from_pixbuf(get_resource_pixbuf("keepnote-32x32.png"))
            self._tray_icon.set_tooltip_text(keepnote.PROGRAM_NAME)
            self._statusicon_menu = self.make_statusicon_menu()
            self._tray_icon.connect("activate", self._on_tray_icon_activate)
            self._tray_icon.connect("popup-menu", self._on_systray_popup_menu)

        self._tray_icon.set_visible(self._app.pref.get("window", "use_systray", default=True))

    def _on_systray_popup_menu(self, status, button, time):
        self._statusicon_menu.popup(None, None, None, None, button, time)

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

    def get_uimanager(self):
        return self._uimanager

    def get_viewer(self):
        return self.viewer

    def get_accel_group(self):
        return self._accel_group

    def get_notebook(self):
        return self.viewer.get_notebook()

    def get_current_node(self):
        return self.viewer.get_current_node()

    # Main window GUI callbacks
    def _on_window_state(self, window, event):
        iconified = self._iconified
        self._iconified = bool(event.new_window_state & Gdk.WindowState.ICONIFIED)

        if not iconified and self._iconified:
            self._was_maximized = self._maximized

        self._maximized = bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)

        if iconified and not self._iconified and self._was_maximized:
            GLib.idle_add(self.maximize)

    def _on_window_size(self, window, allocation):
        if not self._maximized and not self._iconified:
            self._app.pref.get("window")["window_size"] = (allocation.width, allocation.height)

    def _on_tray_icon_activate(self, icon):
        if self.is_active():
            self.minimize_window()
        else:
            self.restore_window()

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

        def on_window_state(window, event):
            if event.new_window_state & Gdk.WindowState.ICONIFIED:
                Gtk.main_quit()
        sig = self.connect("window-state-event", on_window_state)
        self.iconify()
        Gtk.main()
        self.disconnect(sig)

    def restore_window(self):
        self.deiconify()
        self.present()

    def on_new_window(self):
        win = self._app.new_window()
        notebook = self.get_notebook()
        if notebook:
            self._app.ref_notebook(notebook)
            win.set_notebook(notebook)

    # Application preferences
    def load_preferences(self, first_open=False):
        p = self._app.pref
        window_size = p.get("window", "window_size", default=DEFAULT_WINDOW_SIZE)
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
        window_maximized = p.get("window", "window_maximized", default=True)

        self.setup_systray()
        use_systray = p.get("window", "use_systray", default=True)

        if first_open:
            self.resize(*window_size)
            if window_maximized:
                self.maximize()
            if use_systray and p.get("window", "minimize_on_start", default=False):
                self.iconify()

        skip = p.get("window", "skip_taskbar", default=False)
        if use_systray:
            self.set_skip_taskbar_hint(skip)

        self.set_keep_above(p.get("window", "keep_above", default=False))
        if p.get("window", "stick", default=False):
            self.stick()
        else:
            self.unstick()
        # 加载最近的笔记本
        self._recent_notebooks = p.get("recent_notebooks", default=[])
        if first_open and not self._recent_notebooks:
            # 如果是第一次打开且没有最近笔记本，创建一个默认笔记本
            default_path = os.path.join(keepnote.get_user_pref_dir(), "DefaultNotebook")
            if not os.path.exists(default_path):
                self.new_notebook(default_path)
            self._recent_notebooks = [default_path]
        self.set_recent_notebooks_menu(self._recent_notebooks)

        # 确保打开一个笔记本
        if self._recent_notebooks and not self.get_notebook():
            self.open_notebook(self._recent_notebooks[0])

        self._uimanager.set_force_stock(p.get("look_and_feel", "use_stock_icons", default=False))
        self.viewer.load_preferences(self._app.pref, first_open)

    def save_preferences(self):
        p = self._app.pref
        p.set("window", "window_maximized", self._maximized)
        p.set("recent_notebooks", self._recent_notebooks)
        self.viewer.save_preferences(self._app.pref)

    def set_recent_notebooks_menu(self, recent_notebooks):
        menu = self._uimanager.get_widget("/main_menu_bar/File/Open Recent Notebook")
        if not menu.get_submenu():
            submenu = Gtk.Menu()
            submenu.show()
            menu.set_submenu(submenu)
        menu = menu.get_submenu()

        for child in menu.get_children():
            menu.remove(child)

        def make_filename(filename, maxsize=30):
            if len(filename) > maxsize:
                base = os.path.basename(filename)
                pre = max(maxsize - len(base), 10)
                return os.path.join(filename[:pre] + "...", base)
            return filename

        def make_func(filename):
            return lambda w: self.open_notebook(filename)

        # 只添加有效的笔记本路径
        valid_notebooks = [notebook for notebook in recent_notebooks if os.path.exists(notebook)]
        for i, notebook in enumerate(valid_notebooks):
            item = Gtk.MenuItem(label=f"{i + 1}. {make_filename(notebook)}")
            item.connect("activate", make_func(notebook))
            item.show()
            menu.append(item)

        # 如果没有有效的笔记本，显示一个占位符
        if not valid_notebooks:
            item = Gtk.MenuItem(label=_("(No recent notebooks)"))
            item.set_sensitive(False)
            item.show()
            menu.append(item)

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

        # 确保只有一个内容区域
        content_area = dialog.get_content_area()
        content_area.set_border_width(5)
        # 清空可能的多余控件，只保留默认布局
        for child in content_area.get_children():
            if not isinstance(child, Gtk.Box):  # 保留默认的 Box
                content_area.remove(child)

        def on_folder_changed(filechooser):
            folder = unicode_gtk(filechooser.get_current_folder())
            if os.path.exists(os.path.join(folder, notebooklib.PREF_FILE)):
                filechooser.response(Gtk.ResponseType.OK)

        dialog.connect("current-folder-changed", on_folder_changed)

        path = self._app.get_default_path("new_notebook_path")
        if os.path.exists(path):
            dialog.set_current_folder(path)

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
            path = ensure_unicode(dialog.get_current_folder(), FS_ENCODING)
            if path:
                self._app.pref.set("default_paths", "new_notebook_path", os.path.dirname(path))
            notebook_file = ensure_unicode(dialog.get_filename(), FS_ENCODING)
            if notebook_file:
                self.open_notebook(notebook_file)

        dialog.destroy()

    def on_open_notebook_url(self):
        dialog = Gtk.Dialog(title="Open Notebook from URL", parent=self,
                            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)

        p = dialog.get_content_area()
        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        h.show()
        p.pack_start(h, expand=False, fill=True, padding=0)

        l = Gtk.Label(label="URL: ")
        l.show()
        h.pack_start(l, expand=False, fill=True, padding=0)

        entry = Gtk.Entry()
        entry.set_width_chars(80)
        entry.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))
        entry.show()
        h.pack_start(entry, expand=True, fill=True, padding=0)

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
                self._tray_icon.set_visible(False)
        except Exception as e:
            self.error("Error while closing", e, sys.exc_info()[2])
        return False

    def close(self):
        self._on_close()
        self.emit("delete-event", None)
        self.destroy()

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
            # 确保文件名是 Unicode 并规范化路径
            filename = ensure_unicode(filename, FS_ENCODING)
            filename = os.path.normpath(filename)  # 规范化路径分隔符
            print(f"Creating notebook at: {filename}")

            # 检查父目录是否存在且可写
            parent_dir = os.path.dirname(filename)
            if not parent_dir:
                parent_dir = os.getcwd()
            if not os.path.exists(parent_dir):
                raise NoteBookError(f"Parent directory does not exist: '{parent_dir}'")
            if not os.access(parent_dir, os.W_OK):
                raise NoteBookError(f"No write permission for directory: '{parent_dir}'")

            # 检查目标路径是否已存在
            if os.path.exists(filename):
                raise NoteBookError(f"Path already exists: '{filename}'")

            # 创建笔记本
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
        notebook = self._app.get_notebook(filename, self)
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
        if GObject.signal_lookup("cut-clipboard", widget):
            widget.emit("cut-clipboard")

    def on_copy(self):
        widget = self.get_focus()
        if GObject.signal_lookup("copy-clipboard", widget):
            widget.emit("copy-clipboard")

    def on_copy_tree(self):
        widget = self.get_focus()
        if GObject.signal_lookup("copy-tree-clipboard", widget):
            widget.emit("copy-tree-clipboard")

    def on_paste(self):
        widget = self.get_focus()
        if GObject.signal_lookup("paste-clipboard", widget):
            widget.emit("paste-clipboard")

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
        Gtk.AboutDialog.set_url_hook(func, None)

        about = Gtk.AboutDialog()
        about.set_program_name(keepnote.PROGRAM_NAME)
        about.set_version(keepnote.PROGRAM_VERSION_TEXT)
        about.set_copyright(keepnote.COPYRIGHT)
        about.set_logo(get_resource_pixbuf("keepnote-icon.png"))
        about.set_website(keepnote.WEBSITE)
        about.set_license_type(Gtk.License.GPL_2_0)
        about.set_translator_credits(keepnote.TRANSLATOR_CREDITS)

        license_file = keepnote.get_resource("rc", "COPYING")
        if os.path.exists(license_file):
            about.set_license(open(license_file).read())

        about.set_transient_for(self)
        about.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        about.connect("response", lambda d, r: d.destroy())
        about.show()

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
    def get_actions(self):
        actions = [Action(*x) for x in [
            ("File", None, _("_File")),
            ("New Notebook", "gtk-new", _("_New Notebook..."), "", _("Start a new notebook"), lambda w: self.on_new_notebook()),
            ("Open Notebook", "gtk-open", _("_Open Notebook..."), "<control>O", _("Open an existing notebook"), lambda w: self.on_open_notebook()),
            ("Open Recent Notebook", "gtk-open", _("Open Re_cent Notebook")),
            ("Reload Notebook", "gtk-revert-to-saved", _("_Reload Notebook"), "", _("Reload the current notebook"), lambda w: self.reload_notebook()),
            ("Save Notebook", "gtk-save", _("_Save Notebook"), "<control>S", _("Save the current notebook"), lambda w: self._app.save()),
            ("Close Notebook", "gtk-close", _("_Close Notebook"), "", _("Close the current notebook"), lambda w: self._app.close_all_notebook(self.get_notebook())),
            ("Empty Trash", "gtk-delete", _("Empty _Trash"), "", None, lambda w: self.on_empty_trash()),
            ("Export", None, _("_Export Notebook")),
            ("Import", None, _("_Import Notebook")),
            ("Quit", "gtk-quit", _("_Quit"), "<control>Q", _("Quit KeepNote"), lambda w: self.on_quit()),
            ("Edit", None, _("_Edit")),
            ("Undo", "gtk-undo", None, "<control>Z", None, lambda w: self.on_undo()),
            ("Redo", "gtk-redo", None, "<control><shift>Z", None, lambda w: self.on_redo()),
            ("Cut", "gtk-cut", None, "<control>X", None, lambda w: self.on_cut()),
            ("Copy", "gtk-copy", None, "<control>C", None, lambda w: self.on_copy()),
            ("Copy Tree", "gtk-copy", None, "<control><shift>C", None, lambda w: self.on_copy_tree()),
            ("Paste", "gtk-paste", None, "<control>V", None, lambda w: self.on_paste()),
            ("KeepNote Preferences", "gtk-preferences", _("_Preferences"), "", None, lambda w: self._app.app_options_dialog.show(self)),
            ("Search", None, _("_Search")),
            ("Search All Notes", "gtk-find", _("_Search All Notes"), "<control>K", None, lambda w: self.search_box.grab_focus()),
            ("Go", None, _("_Go")),
            ("View", None, _("_View")),
            ("View Note As", "gtk-open", _("_View Note As")),
            ("View Note in File Explorer", "gtk-open", _("View Note in File Explorer"), "", None, lambda w: self.on_view_node_external_app("file_explorer", kind="dir")),
            ("View Note in Text Editor", "gtk-open", _("View Note in Text Editor"), "", None, lambda w: self.on_view_node_external_app("text_editor", kind="page")),
            ("View Note in Web Browser", "gtk-open", _("View Note in Web Browser"), "", None, lambda w: self.on_view_node_external_app("web_browser", kind="page")),
            ("Open File", "gtk-open", _("_Open File"), "", None, lambda w: self.on_view_node_external_app("file_launcher", kind="file")),
            ("Tools", None, _("_Tools")),
            ("Update Notebook Index", None, _("_Update Notebook Index"), "", None, lambda w: self.update_index(clear=True)),
            ("Compact Notebook Index", None, _("_Compact Notebook Index"), "", None, lambda w: self.compact_index()),
            ("Open Notebook URL", None, _("_Open Notebook from URL"), "", None, lambda w: self.on_open_notebook_url()),
            ("Window", None, _("Window")),
            ("New Window", None, _("New Window"), "", _("Open a new window"), lambda w: self.on_new_window()),
            ("Close Window", None, _("Close Window"), "", _("Close window"), lambda w: self.close()),
            ("Help", None, _("_Help")),
            ("View Error Log...", "gtk-dialog-error", _("View _Error Log..."), "", None, lambda w: self.view_error_log()),
            ("View Preference Files...", None, _("View Preference Files..."), "", None, lambda w: self.view_config_files()),
            ("Drag and Drop Test...", None, _("Drag and Drop Test..."), "", None, lambda w: self.drag_test.on_drag_and_drop_test()),
            ("About", "gtk-about", _("_About"), "", None, lambda w: self.on_about())
        ]] + [
            Action("Main Spacer Tool"),
            Action("Search Box Tool", None, None, "", _("Search All Notes")),
            Action("Search Button Tool", "gtk-find", None, "", _("Search All Notes"), lambda w: self.search_box.on_search_nodes())
        ]

        recent = next(x for x in actions if x.get_property("name") == "Open Recent Notebook")
        recent.set_property("is-important", True)
        return actions

    def setup_menus(self, uimanager):
        pass

    def get_ui(self):
        return ["""
<ui>
<!-- main window menu bar -->
<menubar name="main_menu_bar">
  <menu action="File">
     <menuitem action="New Notebook"/>
     <placeholder name="Viewer"/>
     <placeholder name="New"/>
     <separator/>
     <menuitem action="Open Notebook"/>
     <menuitem action="Open Recent Notebook"/>
     <menuitem action="Save Notebook"/>
     <menuitem action="Close Notebook"/>
     <menuitem action="Reload Notebook"/>
     <menuitem action="Empty Trash"/>
     <separator/>
     <menu action="Export" />
     <menu action="Import" />
     <separator/>
     <placeholder name="Extensions"/>
     <separator/>
     <menuitem action="Quit"/>
  </menu>
  <menu action="Edit">
    <menuitem action="Undo"/>
    <menuitem action="Redo"/>
    <separator/>
    <menuitem action="Cut"/>
    <menuitem action="Copy"/>
    <menuitem action="Copy Tree"/>
    <menuitem action="Paste"/>
    <separator/>
    <placeholder name="Viewer"/>
    <separator/>
    <menuitem action="KeepNote Preferences"/>
  </menu>
  <menu action="Search">
    <menuitem action="Search All Notes"/>
    <placeholder name="Viewer"/>
  </menu>
  <placeholder name="Viewer"/>
  <menu action="Go">
    <placeholder name="Viewer"/>
  </menu>
  <menu action="Tools">
    <placeholder name="Viewer"/>
    <menuitem action="Update Notebook Index"/>
    <menuitem action="Compact Notebook Index"/>
    <menuitem action="Open Notebook URL"/>
    <placeholder name="Extensions"/>
  </menu>
  <menu action="Window">
     <menuitem action="New Window"/>
     <menuitem action="Close Window"/>
     <placeholder name="Viewer Window"/>
  </menu>
  <menu action="Help">
    <menuitem action="View Error Log..."/>
    <menuitem action="View Preference Files..."/>
    <menuitem action="Drag and Drop Test..."/>
    <separator/>
    <menuitem action="About"/>
  </menu>
</menubar>
<!-- main window tool bar -->
<toolbar name="main_tool_bar">
  <placeholder name="Viewer"/>
  <toolitem action="Main Spacer Tool"/>
  <toolitem action="Search Box Tool"/>
  <toolitem action="Search Button Tool"/>
</toolbar>
<!-- popup menus -->
<menubar name="popup_menus">
</menubar>
</ui>
"""]

    def get_actions_statusicon(self):
        return [Action(*x) for x in [
            ("KeepNote Preferences", "gtk-preferences", _("_Preferences"), "", None, lambda w: self._app.app_options_dialog.show(self)),
            ("Quit", "gtk-quit", _("_Quit"), "<control>Q", _("Quit KeepNote"), lambda w: self.close()),
            ("About", "gtk-about", _("_About"), "", None, lambda w: self.on_about())
        ]]

    def get_ui_statusicon(self):
        return ["""
<ui>
  <!-- statusicon_menu -->
  <popup name="statusicon_menu">
    <menuitem action="KeepNote Preferences"/>
    <menuitem action="About"/>
    <separator/>
    <menuitem action="Quit"/>
  </popup>
</ui>
"""]

    def make_menubar(self):
        self._actiongroup = Gtk.ActionGroup(name='MainWindow')
        self._uimanager.insert_action_group(self._actiongroup, 0)
        add_actions(self._actiongroup, self.get_actions())
        for s in self.get_ui():
            self._uimanager.add_ui_from_string(s)
        self.setup_menus(self._uimanager)
        return self._uimanager.get_widget('/main_menu_bar')

    def make_toolbar(self):
        toolbar = self._uimanager.get_widget('/main_tool_bar')
        toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
        toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        toolbar.set_border_width(0)
        try:
            toolbar.set_icon_size(Gtk.IconSize.SMALL_TOOLBAR)
        except:
            pass

        spacer = self._uimanager.get_widget("/main_tool_bar/Main Spacer Tool")
        spacer.remove(spacer.get_child())
        spacer.set_expand(True)

        self.search_box = SearchBox(self)
        self.search_box.show()
        w = self._uimanager.get_widget("/main_tool_bar/Search Box Tool")
        w.remove(w.get_child())
        w.add(self.search_box)

        return toolbar

    def make_statusicon_menu(self):
        self._actiongroup_statusicon = Gtk.ActionGroup(name='StatusIcon')
        self._tray_icon.uimanager = Gtk.UIManager()
        self._tray_icon.uimanager.insert_action_group(self._actiongroup_statusicon, 0)
        add_actions(self._actiongroup_statusicon, self.get_actions_statusicon())
        for s in self.get_ui_statusicon():
            self._tray_icon.uimanager.add_ui_from_string(s)
        self.setup_menus(self._tray_icon.uimanager)

        return self._tray_icon.uimanager.get_widget('/statusicon_menu')





GObject.type_register(KeepNoteWindow)
GObject.signal_new("error", KeepNoteWindow, GObject.SignalFlags.RUN_LAST, None, (str, object, object))


class SearchBox(Gtk.Entry):
    def __init__(self, window):
        super().__init__()

        self._window = window
        self.connect("changed", self._on_search_box_text_changed)
        self.connect("activate", lambda w: self.on_search_nodes())

        self.search_box_list = Gtk.ListStore(str, str)
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