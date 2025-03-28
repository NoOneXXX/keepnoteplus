
# PyGObject imports
from gi import require_version
require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

# KeepNote imports
from keepnote.gui import treemodel
from keepnote.gui import basetreeview


class KeepNoteTreeView(basetreeview.KeepNoteBaseTreeView):
    """
    TreeView widget for the KeepNote NoteBook
    """

    def __init__(self):
        super().__init__()

        self._notebook = None

        self.set_model(treemodel.KeepNoteTreeModel())

        # Treeview signals
        self.connect("key-release-event", self.on_key_released)
        self.connect("button-press-event", self.on_button_press)

        # Selection config
        self.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        # Tree style
        self.set_headers_visible(False)
        self.set_property("enable-tree-lines", True)  # GTK+ 3 supports this property

        self._setup_columns()
        self.set_sensitive(False)

    def _setup_columns(self):
        self.clear_columns()

        if self._notebook is None:
            return

        # Create the treeview column
        self.column = Gtk.TreeViewColumn()
        self.column.set_clickable(False)
        self.append_column(self.column)

        self._add_model_column("title")
        self._add_title_render(self.column, "title")

        # Make treeview searchable
        self.set_search_column(self.model.get_column_by_name("title").pos)

    # GUI callbacks
    def on_key_released(self, widget, event):
        """Process key presses"""
        if self.editing_path:
            return

        if event.keyval == Gdk.KEY_Delete:
            self.emit("delete-node", self.get_selected_nodes())
            self.stop_emission_by_name("key-release-event")

    def on_button_press(self, widget, event):
        """Process context popup menu"""
        if event.button == 3:
            # Popup menu
            return self.popup_menu(event.x, event.y, event.button, event.time)

        if event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
            nodes = self.get_selected_nodes()
            if nodes:
                # Double click --> goto node
                self.emit("activate-node", nodes[0])

    # Actions
    def set_notebook(self, notebook):
        basetreeview.KeepNoteBaseTreeView.set_notebook(self, notebook)

        if self._notebook is None:
            self.model.set_root_nodes([])
            self.set_sensitive(False)
        else:
            self.set_sensitive(True)
            root = self._notebook
            model = self.model

            self.set_model(None)
            model.set_root_nodes([root])
            self.set_model(model)

            self._setup_columns()

            if root.get_attr("expanded", True):
                path = Gtk.TreePath.new_from_indices([0])  # 创建 Gtk.TreePath 对象
                self.expand_to_path(path)

    def edit_node(self, node):
        path = treemodel.get_path_from_node(
            self.model, node,
            self.rich_model.get_node_column_pos())
        GLib.idle_add(lambda: self.set_cursor_on_cell(
            path, self.column, self.title_text, True))