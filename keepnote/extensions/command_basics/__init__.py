"""
KeepNote Extension
backup_tar

Command-line basic commands
"""

# Python imports
import os
import sys
import time

# PyGObject imports for GTK 4
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib

# KeepNote imports
import keepnote
from keepnote import AppCommand
import keepnote.notebook
import keepnote.notebook.update
import keepnote.extension
import keepnote.gui.extension


class Extension(keepnote.gui.extension.Extension):

    def __init__(self, app):
        """Initialize extension"""

        keepnote.gui.extension.Extension.__init__(self, app)
        self.app = app
        self.enabled.add(self.on_enabled)

        self.commands = [
            # window commands
            AppCommand("focus", lambda app, args: app.focus_windows(),
                       help="focus all open windows"),
            AppCommand("minimize", self.on_minimize_windows,
                       help="minimize all windows"),
            AppCommand("toggle-windows", self.on_toggle_windows,
                       help="toggle all windows"),

            # extension commands
            AppCommand("install", self.on_install_extension,
                       metavar="FILENAME",
                       help="install a new extension"),
            AppCommand("uninstall", self.on_uninstall_extension,
                       metavar="EXTENSION_NAME",
                       help="uninstall an extension"),
            AppCommand("tmp_ext", self.on_temp_extension,
                       metavar="FILENAME",
                       help="add an extension just for this session"),
            AppCommand("ext_path", self.on_extension_path,
                       metavar="PATH",
                       help="add an extension path for this session"),
            AppCommand("quit", lambda app, args:
            GLib.idle_add(app.quit),
                       help="close all KeepNote windows"),

            # notebook commands
            AppCommand("view", self.on_view_note,
                       metavar="NOTE_URL",
                       help="view a note"),
            AppCommand("new", self.on_new_note,
                       metavar="PARENT_URL",
                       help="add a new note"),
            AppCommand("search-titles", self.on_search_titles,
                       metavar="TEXT",
                       help="search notes by title"),
            AppCommand("upgrade", self.on_upgrade_notebook,
                       metavar="[v VERSION] NOTEBOOK...",
                       help="upgrade a notebook"),
            AppCommand("backup", self.on_backup_notebook,
                       metavar="NOTEBOOK [ARCHIVE_NAME]",
                       help="backup a notebook to a tar archive"),

            # misc
            AppCommand("screenshot", self.on_screenshot,
                       help="insert a new screenshot"),
        ]

    def get_depends(self):
        return [("keepnote", ">=", (0, 6, 4))]

    def on_enabled(self, enabled):
        if enabled:
            for command in self.commands:
                if self.app.get_command(command.name):
                    continue
                try:
                    self.app.add_command(command)
                except Exception as e:
                    self.app.error(f"Could not add command '{command.name}'", e, sys.exc_info()[2])
        else:
            for command in self.commands:
                self.app.remove_command(command.name)

    def error(self, message):
        """Print an error message to stderr"""
        print(f"Error: {message}", file=sys.stderr)

    # ====================================================
    # commands

    def on_minimize_windows(self, app, args):
        for window in app.get_windows():
            window.minimize()

    def on_toggle_windows(self, app, args):
        for window in app.get_windows():
            if window.is_active():
                self.on_minimize_windows(app, args)
                return
        app.focus_windows()

    def on_uninstall_extension(self, app, args):
        if len(args) < 2:
            self.error("Must specify extension name")
            return

        for extname in args[1:]:
            try:
                app.uninstall_extension(extname)
                print(f"Successfully uninstalled extension '{extname}'")
            except Exception as e:
                self.error(f"Failed to uninstall extension '{extname}': {str(e)}")

    def on_install_extension(self, app, args):
        if len(args) < 2:
            self.error("Must specify extension filename")
            return

        for filename in args[1:]:
            try:
                app.install_extension(filename)
                print(f"Successfully installed extension from '{filename}'")
            except Exception as e:
                self.error(f"Failed to install extension from '{filename}': {str(e)}")

    def on_temp_extension(self, app, args):
        if len(args) < 2:
            self.error("Must specify extension filename")
            return

        for filename in args[1:]:
            try:
                entry = app.add_extension(filename, "temp")
                ext = app.get_extension(entry.get_key())
                if ext:
                    app.init_extensions_windows(windows=None, exts=[ext])
                    ext.enable(True)
                    print(f"Successfully added temporary extension from '{filename}'")
                else:
                    self.error(f"Could not load extension from '{filename}'")
            except Exception as e:
                self.error(f"Failed to add temporary extension from '{filename}': {str(e)}")

    def on_extension_path(self, app, args):
        if len(args) < 2:
            self.error("Must specify extension path")
            return

        exts = []
        for extensions_dir in args[1:]:
            try:
                for filename in keepnote.extension.iter_extensions(extensions_dir):
                    entry = app.add_extension_entry(filename, "temp")
                    ext = app.get_extension(entry.get_key())
                    if ext:
                        exts.append(ext)
            except Exception as e:
                self.error(f"Failed to load extensions from '{extensions_dir}': {str(e)}")
                continue

        try:
            app.init_extensions_windows(windows=None, exts=exts)
            for ext in exts:
                ext.enable(True)
            print(f"Successfully added {len(exts)} extensions from path(s): {', '.join(args[1:])}")
        except Exception as e:
            self.error(f"Failed to enable extensions: {str(e)}")

    def on_screenshot(self, app, args):
        window = app.get_current_window()
        if not window:
            self.error("No active window found")
            return

        editor = window.get_viewer().get_editor()
        if hasattr(editor, "get_editor"):
            editor = editor.get_editor()

        if hasattr(editor, "on_screenshot"):
            try:
                editor.on_screenshot()
                print("Screenshot inserted successfully")
            except Exception as e:
                self.error(f"Failed to insert screenshot: {str(e)}")
        else:
            self.error("Editor does not support screenshot insertion")

    def on_view_note(self, app, args):
        if len(args) < 2:
            self.error("Must specify note URL")
            return

        app.focus_windows()

        nodeurl = args[1]
        if keepnote.notebook.is_node_url(nodeurl):
            host, nodeid = keepnote.notebook.parse_node_url(nodeurl)
            self.view_nodeid(app, nodeid)
        else:
            # do text search
            window = self.app.get_current_window()
            if window is None:
                return
            notebook = window.get_notebook()
            if notebook is None:
                return

            results = list(notebook.search_node_titles(nodeurl))

            if len(results) == 1:
                self.view_nodeid(app, results[0][0])
            else:
                viewer = window.get_viewer()
                viewer.start_search_result()
                for nodeid, title in results:
                    node = notebook.get_node_by_id(nodeid)
                    if node:
                        viewer.add_search_result(node)

    def on_new_note(self, app, args):
        if len(args) < 2:
            self.error("Must specify note URL")
            return

        app.focus_windows()

        nodeurl = args[1]
        window, notebook = self.get_window_notebook()
        nodeid = self.get_nodeid(nodeurl)
        if notebook and nodeid:
            node = notebook.get_node_by_id(nodeid)
            if node:
                window.get_viewer().new_node(
                    keepnote.notebook.CONTENT_TYPE_PAGE, "child", node)

    def on_search_titles(self, app, args):
        if len(args) < 2:
            self.error("Must specify text to search")
            return

        # get window and notebook
        window = self.app.get_current_window()
        if window is None:
            return
        notebook = window.get_notebook()
        if notebook is None:
            return

        # do search
        text = args[1]
        nodes = list(notebook.search_node_titles(text))
        for nodeid, title in nodes:
            print(f"{title}\t{keepnote.notebook.get_node_url(nodeid)}")

    def on_backup_notebook(self, app, args):
        if len(args) < 2:
            self.error("Must specify notebook path")
            return

        notebook_path = args[1]
        if not os.path.exists(notebook_path):
            self.error(f"Notebook path does not exist: {notebook_path}")
            return

        # Determine archive name
        if len(args) >= 3:
            archive_name = args[2]
        else:
            archive_name = f"{os.path.basename(notebook_path)}-{time.strftime('%Y%m%d')}.tar.gz"

        try:
            import tarfile
            with tarfile.open(archive_name, "w:gz") as tar:
                tar.add(notebook_path, arcname=os.path.basename(notebook_path))
            print(f"Successfully created backup: {archive_name}")
        except Exception as e:
            self.error(f"Failed to create backup '{archive_name}': {str(e)}")

    def view_nodeid(self, app, nodeid):
        for window in app.get_windows():
            notebook = window.get_notebook()
            if not notebook:
                continue
            node = notebook.get_node_by_id(nodeid)
            if node:
                window.get_viewer().goto_node(node)
                break

    def get_nodeid(self, text):
        if keepnote.notebook.is_node_url(text):
            host, nodeid = keepnote.notebook.parse_node_url(text)
            return nodeid
        else:
            # do text search
            window = self.app.get_current_window()
            if window is None:
                return None
            notebook = window.get_notebook()
            if notebook is None:
                return None

            results = list(notebook.search_node_titles(text))

            if len(results) == 1:
                return results[0][0]
            else:
                for nodeid, title in results:
                    if title == text:
                        return nodeid
                return None

    def get_window_notebook(self):
        window = self.app.get_current_window()
        if window is None:
            return None, None
        notebook = window.get_notebook()
        return window, notebook

    def on_upgrade_notebook(self, app, args):
        version = keepnote.notebook.NOTEBOOK_FORMAT_VERSION
        i = 1
        while i < len(args):
            if args[i] == "v":
                try:
                    version = int(args[i + 1])
                    i += 2
                except (IndexError, ValueError):
                    self.error("Expected version number after 'v'")
                    return
            else:
                break

        files = args[i:]
        if not files:
            self.error("Must specify at least one notebook to upgrade")
            return

        for filename in files:
            keepnote.log_message(f"Upgrading notebook to version {version}: {filename}\n")
            try:
                keepnote.notebook.update.update_notebook(filename, version, verify=True)
                print(f"Successfully upgraded notebook: {filename}")
            except Exception as e:
                self.error(f"Failed to upgrade notebook '{filename}': {str(e)}")