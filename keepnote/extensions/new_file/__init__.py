"""
KeepNote Extension
new_file

Extension allows adding new filetypes to a notebook
"""

import gettext
import os
import re
import shutil
import sys
import time
import xml.etree.cElementTree as etree

_ = gettext.gettext

import keepnote
from keepnote import unicode_gtk
from keepnote.notebook import NoteBookError
from keepnote import notebook as notebooklib
from keepnote import tasklib
from keepnote import tarfile
from keepnote.gui import extension
from keepnote.gui import dialog_app_options

# PyGObject imports for GTK 4
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio

class Extension(extension.Extension):

    def __init__(self, app):
        """Initialize extension"""
        extension.Extension.__init__(self, app)
        self.app = app

        self._file_types = []
        self._default_file_types = [
            FileType("Text File (txt)", "untitled.txt", "plain_text.txt"),
            FileType("Spreadsheet (xls)", "untitled.xls", "spreadsheet.xls"),
            FileType("Word Document (doc)", "untitled.doc", "document.doc")
        ]

        self.enabled.add(self.on_enabled)

    def get_filetypes(self):
        return self._file_types

    def on_enabled(self, enabled):
        if enabled:
            self.load_config()

    def get_depends(self):
        return [("keepnote", ">=", (0, 7, 1))]

    #===============================
    # Config handling

    def get_config_file(self):
        return self.get_data_file("config.xml")

    def load_config(self):
        config = self.get_config_file()
        if not os.path.exists(config):
            self.set_default_file_types()
            self.save_default_example_files()
            self.save_config()

        try:
            tree = etree.ElementTree(file=config)
            root = tree.getroot()
            if root.tag != "file_types":
                raise NoteBookError("Root tag is not 'file_types'")

            self._file_types = []
            for child in root:
                if child.tag == "file_type":
                    filetype = FileType("", "", "")
                    for child2 in child:
                        if child2.tag == "name":
                            filetype.name = child2.text
                        elif child2.tag == "filename":
                            filetype.filename = child2.text
                        elif child2.tag == "example_file":
                            filetype.example_file = child2.text
                    self._file_types.append(filetype)

        except Exception:
            self.app.error("Error reading file type configuration")
            self.set_default_file_types()

        self.save_config()

    def save_config(self):
        config = self.get_config_file()
        tree = etree.ElementTree(etree.Element("file_types"))
        root = tree.getroot()

        for file_type in self._file_types:
            elm = etree.SubElement(root, "file_type")
            name = etree.SubElement(elm, "name")
            name.text = file_type.name
            example = etree.SubElement(elm, "example_file")
            example.text = file_type.example_file
            filename = etree.SubElement(elm, "filename")
            filename.text = file_type.filename

        # Write the XML file with proper encoding
        with open(config, "wb") as f:
            tree.write(f, encoding="utf-8", xml_declaration=True)

    def set_default_file_types(self):
        self._file_types = list(self._default_file_types)

    def save_default_example_files(self):
        base = self.get_base_dir()
        data_dir = self.get_data_dir()
        for file_type in self._default_file_types:
            fn = file_type.example_file
            shutil.copy(os.path.join(base, fn), os.path.join(data_dir, fn))

    def update_all_menus(self):
        for window in self.get_windows():
            self.set_new_file_menus(window)

    #==============================
    # UI

    def on_add_ui(self, window):
        """Initialize extension for a particular window"""
        # Add "New File" action
        action = Gio.SimpleAction.new("new-file", None)
        action.connect("activate", lambda action, param: None)
        window.add_action(action)

        # Add menu items using GMenu
        app = window.get_application()
        menu = app.get_menubar()
        if not menu:
            menu = Gio.Menu()
            app.set_menubar(menu)

        file_menu = None
        for i in range(menu.get_n_items()):
            if menu.get_item_attribute_value(i, "label").get_string() == "_File":
                file_menu = menu.get_item_link(i, "submenu")
                break

        if not file_menu:
            file_menu = Gio.Menu()
            menu.append_submenu("_File", file_menu)

        new_menu = None
        for i in range(file_menu.get_n_items()):
            if file_menu.get_item_attribute_value(i, "label") == "New":
                new_menu = file_menu.get_item_link(i, "submenu")
                break

        if not new_menu:
            new_menu = Gio.Menu()
            file_menu.append_submenu("New", new_menu)

        new_menu.append("New _File", "win.new-file")
        self.set_new_file_menus(window)

    #=================================
    # Options UI setup

    def on_add_options_ui(self, dialog):
        dialog.add_section(NewFileSection("new_file", dialog, self._app, self), "extensions")

    def on_remove_options_ui(self, dialog):
        dialog.remove_section("new_file")

    #======================================
    # Callbacks

    def on_new_file(self, window, file_type):
        """Callback from GUI to add a new file"""
        notebook = window.get_notebook()
        if notebook is None:
            return

        nodes = window.get_selected_nodes()
        if len(nodes) == 0:
            parent = notebook
        else:
            sibling = nodes[0]
            if sibling.get_parent():
                parent = sibling.get_parent()
                index = sibling.get_attr("order") + 1
            else:
                parent = sibling

        try:
            uri = os.path.join(self.get_data_dir(), file_type.example_file)
            node = notebooklib.attach_file(uri, parent)
            node.rename(file_type.filename)
            window.get_viewer().goto_node(node)
        except Exception as e:
            window.error("Error while attaching file '%s'." % uri, e)

    def on_new_file_type(self, window):
        """Callback from GUI for adding a new file type"""
        self.app.app_options_dialog.show(window, "new_file")

    #==========================================
    # Menu setup

    def set_new_file_menus(self, window):
        """Set the new file menus in the file menu"""
        app = window.get_application()
        menu = app.get_menubar()
        if not menu:
            return

        file_menu = None
        for i in range(menu.get_n_items()):
            if menu.get_item_attribute_value(i, "label").get_string() == "_File":
                file_menu = menu.get_item_link(i, "submenu")
                break

        if not file_menu:
            return

        new_menu = None
        for i in range(file_menu.get_n_items()):
            if file_menu.get_item_attribute_value(i, "label") == "New":
                new_menu = file_menu.get_item_link(i, "submenu")
                break

        if new_menu:
            for i in range(new_menu.get_n_items()):
                if new_menu.get_item_attribute_value(i, "label").get_string() == "New _File":
                    submenu = Gio.Menu()
                    for file_type in self._file_types:
                        action_name = f"new-file-{file_type.name.lower().replace(' ', '-')}"
                        action = Gio.SimpleAction.new(action_name, None)
                        action.connect("activate", lambda action, param, ft=file_type: self.on_new_file(window, ft))
                        window.add_action(action)
                        submenu.append(f"New {file_type.name}", f"win.{action_name}")

                    submenu.append(None, None)  # Separator
                    action = Gio.SimpleAction.new("add-new-file-type", None)
                    action.connect("activate", lambda action, param: self.on_new_file_type(window))
                    window.add_action(action)
                    submenu.append("Add New File Type", "win.add-new-file-type")

                    new_menu.remove(i)
                    new_menu.insert_submenu(i, "New _File", submenu)
                    break

    def set_new_file_menu(self, window, menu):
        """Set the new file submenu"""
        pass  # Handled in set_new_file_menus with GMenu

    #===============================
    # Actions

    def install_example_file(self, filename):
        """Installs a new example file into the extension"""
        newpath = self.get_data_dir()
        newfilename = os.path.basename(filename)
        newfilename, ext = os.path.splitext(newfilename)
        newfilename = notebooklib.get_unique_filename(newpath, newfilename, ext=ext, sep="", number=2)
        shutil.copy(filename, newfilename)
        return os.path.basename(newfilename)

class FileType(object):
    """Class containing information about a filetype"""
    def __init__(self, name, filename, example_file):
        self.name = name
        self.filename = filename
        self.example_file = example_file

    def copy(self):
        return FileType(self.name, self.filename, self.example_file)

class NewFileSection(dialog_app_options.Section):
    def __init__(self, key, dialog, app, ext, label="New File Types", icon=None):
        dialog_app_options.Section.__init__(self, key, dialog, app, label, icon)
        self.ext = ext
        self._filetypes = []
        self._current_filetype = None

        # Setup UI
        w = self.get_default_widget()
        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        w.append(h)

        # Left column (file type list)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        h.append(v)

        self.filetype_store = Gtk.ListStore.new([str, object])
        self.filetype_listview = Gtk.TreeView(model=self.filetype_store)
        self.filetype_listview.set_headers_visible(False)
        self.filetype_listview.get_selection().connect("changed", self.on_listview_select)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_has_frame(True)
        sw.set_child(self.filetype_listview)
        sw.set_size_request(160, 200)
        v.append(sw)

        column = Gtk.TreeViewColumn()
        self.filetype_listview.append_column(column)
        cell_text = Gtk.CellRendererText()
        column.pack_start(cell_text, True)
        column.add_attribute(cell_text, 'text', 0)

        # Add/del buttons
        h2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        v.append(h2)

        button = Gtk.Button(label="New")
        button.connect("clicked", self.on_new_filetype)
        h2.append(button)

        button = Gtk.Button(label="Delete")
        button.connect("clicked", self.on_delete_filetype)
        h2.append(button)

        # Right column (file type editor)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        h.append(v)

        table = Gtk.Grid()
        table.set_row_spacing(5)
        table.set_column_spacing(5)
        self.filetype_editor = table
        v.append(table)

        label = Gtk.Label(label="File type name:")
        table.attach(label, 0, 0, 1, 1)

        self.filetype = Gtk.Entry()
        table.attach(self.filetype, 1, 0, 1, 1)

        label = Gtk.Label(label="Default filename:")
        table.attach(label, 0, 1, 1, 1)

        self.filename = Gtk.Entry()
        table.attach(self.filename, 1, 1, 1, 1)

        label = Gtk.Label(label="Example new file:")
        table.attach(label, 0, 2, 1, 1)

        self.example_file = Gtk.Entry()
        table.attach(self.example_file, 1, 2, 1, 1)

        button = Gtk.Button(label=_("Browse..."))
        button.set_icon_name("document-open")
        button.connect("clicked", lambda w: dialog_app_options.on_browse(
            w.get_root(), "Choose Example New File", "", self.example_file))
        table.attach(button, 1, 3, 1, 1)

        self.set_filetypes()
        self.set_filetype_editor(None)

    def load_options(self, app):
        self._filetypes = [x.copy() for x in self.ext.get_filetypes()]
        self.set_filetypes()
        self.filetype_listview.get_selection().unselect_all()

    def save_options(self, app):
        self.save_current_filetype()
        bad = []
        for filetype in self._filetypes:
            if os.path.isabs(filetype.example_file):
                try:
                    filetype.example_file = self.ext.install_example_file(filetype.example_file)
                except Exception as e:
                    app.error("Cannot install example file '%s'" % filetype.example_file, e)
                    bad.append(filetype)

        self.ext.get_filetypes()[:] = [x.copy() for x in self._filetypes if x not in bad]
        self.ext.save_config()
        self.ext.update_all_menus()

    def set_filetypes(self):
        if self.filetype_store is not None:
            self.filetype_store.clear()
            for filetype in self._filetypes:
                self.filetype_store.append([filetype.name, filetype])
        else:
            self.filetype_store = Gtk.ListStore.new([str, object])
            self.filetype_listview.set_model(self.filetype_store)

    def set_filetype_editor(self, filetype):
        if filetype is None:
            self._current_filetype = None
            self.filetype.set_text("")
            self.filename.set_text("")
            self.example_file.set_text("")
            self.filetype_editor.set_sensitive(False)
        else:
            self._current_filetype = filetype
            self.filetype.set_text(filetype.name)
            self.filename.set_text(filetype.filename)
            self.example_file.set_text(filetype.example_file)
            self.filetype_editor.set_sensitive(True)

    def save_current_filetype(self):
        if self._current_filetype:
            self._current_filetype.name = self.filetype.get_text()
            self._current_filetype.filename = self.filename.get_text()
            self._current_filetype.example_file = self.example_file.get_text()
            for row in self.filetype_store:
                if row[1] == self._current_filetype:
                    row[0] = self._current_filetype.name

    def on_listview_select(self, selection):
        model, it = self.filetype_listview.get_selection().get_selected()
        self.save_current_filetype()
        if it is not None:
            filetype = self.filetype_store[it][1]
            self.set_filetype_editor(filetype)
        else:
            self.set_filetype_editor(None)

    def on_new_filetype(self, button):
        self._filetypes.append(FileType("New File Type", "untitled", ""))
        self.set_filetypes()
        self.filetype_listview.set_cursor(len(self._filetypes)-1)

    def on_delete_filetype(self, button):
        model, it = self.filetype_listview.get_selection().get_selected()
        if it is not None:
            filetype = self.filetype_store[it][1]
            self._filetypes.remove(filetype)
            self.set_filetypes()