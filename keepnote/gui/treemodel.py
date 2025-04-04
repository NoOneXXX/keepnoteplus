# PyGObject imports
from gi import require_version
require_version('Gtk', '4.0')  # GTK4 change
from gi.repository import GObject
from gi.repository import Gtk, GdkPixbuf  # GTK4 change
import os

from keepnote import get_resource

def get_path_from_node(model, node, node_col):
    """
    Determine the path of a NoteBookNode 'node' in a gtk.TreeModel 'model'
    """
    if node is None:
        return ()

    def find_iter(model, target_node, parent_iter=None):
        """Recursively find the TreeIter for a given node"""
        iter = model.iter_children(parent_iter)
        while iter is not None:
            current_node = model.get_value(iter, node_col)
            if current_node == target_node:
                return iter
            # Recursively search children
            child_iter = find_iter(model, target_node, iter)
            if child_iter is not None:
                return child_iter
            iter = model.iter_next(iter)
        return None

    # Find the TreeIter for the target node
    target_iter = find_iter(model, node)
    if target_iter is None:
        return None  # Node is not in the model

    # Get the path from the TreeIter
    path = model.get_path(target_iter)
    return tuple(path)  # 转换为元组以保持兼容性


class TreeModelColumn(object):
    def __init__(self, name, datatype, attr=None, get=lambda node: ""):
        self.pos = None
        self.name = name
        self.type = datatype
        self.attr = attr
        self.get_value = get

def iter_children(model, it):
    """Iterate through the children of a row (it)"""
    node = model.iter_children(it)
    while node:
        yield node
        node = model.iter_next(node)

class BaseTreeModel(Gtk.TreeStore):
    def __init__(self, roots=[]):
        super().__init__(object, str, GdkPixbuf.Pixbuf, str, str, GdkPixbuf.Pixbuf)  # 6 列
        self._notebook = None
        self._roots = []
        self._root_set = {}
        self._master_node = None
        self._nested = True

        self._columns = []
        self._columns_lookup = {}
        self._node_column = None

        self.set_root_nodes(roots)

        self.append_column(TreeModelColumn("node", object, get=lambda node: node))
        self.append_column(TreeModelColumn("title", str, get=lambda node: node.get_title() if node else ""))
        self.append_column(TreeModelColumn("icon", GdkPixbuf.Pixbuf, get=self._get_node_icon))
        self.append_column(TreeModelColumn("bgcolor", str,
                                           get=lambda node: node.get_attr("background") if node and node.get_attr(
                                               "background") else ""))
        self.append_column(TreeModelColumn("fgcolor", str,
                                           get=lambda node: node.get_attr("foreground") if node and node.get_attr(
                                               "foreground") else ""))
        self.append_column(TreeModelColumn("icon_open", GdkPixbuf.Pixbuf, get=self._get_expander_icon))
        self.set_node_column(self.get_column_by_name("node"))
        print(f"Initialized BaseTreeModel with {self.get_n_columns()} columns")

    def _get_expander_icon(self, node):
        if not node or not node.has_children():
            return None
        icon_name = node.get_attr("icon_open") or "folder-open.png"
        try:
            icon_path = get_resource("images", os.path.join("node_icons", icon_name))
            print(f"Loading expander icon from: {icon_path}")
            return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 16, 16)
        except Exception as e:
            print(f"Failed to load expander icon {icon_name}: {e}")
            return None

    def set_notebook(self, notebook):
        if self._notebook is not None:
            self._notebook.node_changed.remove(self._on_node_changed)

        self._notebook = notebook

        if self._notebook:
            self._notebook.node_changed.add(self._on_node_changed)

    def _get_node_icon(self, node):
        if not node:
            return None
        icon_name = node.get_attr("icon") or "note.png"
        try:
            icon_path = get_resource("images", os.path.join("node_icons", icon_name))
            print(f"Loading icon from: {icon_path}")
            return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 16, 16)
        except Exception as e:
            print(f"Failed to load icon {icon_name}: {e}")
            return None

    # Column manipulation
    def append_column(self, column):
        assert column.name not in self._columns_lookup
        column.pos = len(self._columns)
        self._columns.append(column)
        self._columns_lookup[column.name] = column

    def get_column(self, pos):
        return self._columns[pos]

    def get_columns(self):
        return self._columns

    def get_column_by_name(self, colname):
        return self._columns_lookup.get(colname, None)

    def add_column(self, name, coltype, get):
        col = self.get_column_by_name(name)
        if col is None:
            col = TreeModelColumn(name, coltype, get=get)
            self.append_column(col)
        return col

    def get_node_column_pos(self):
        assert self._node_column is not None
        return self._node_column.pos

    def get_node_column(self):
        return self._node_column

    def set_node_column(self, col):
        self._node_column = col

    def set_master_node(self, node):
        self._master_node = node

    def get_master_node(self):
        return self._master_node

    def set_nested(self, nested):
        self._nested = nested
        self.set_root_nodes(self._roots)

    def get_nested(self):
        return self._nested

    def clear(self):
        super().clear()
        self._roots = []
        self._root_set = {}

    def set_root_nodes(self, roots=[]):
        self.clear()
        for node in roots:
            self.append(node)
        if len(roots) > 0:
            assert self._notebook is not None

    def get_root_nodes(self):
        return self._roots

    def append(self, node):
        index = len(self._roots)
        self._root_set[node] = index
        self._roots.append(node)
        title = node.get_title() if node else ""
        icon = self._get_node_icon(node)
        bgcolor = node.get_attr("background") if node and node.get_attr("background") else None
        fgcolor = node.get_attr("foreground") if node and node.get_attr("foreground") else None
        icon_open = self._get_expander_icon(node)
        rowref = super().append(None, [node, title, icon, bgcolor, fgcolor, icon_open])
        print(
            f"Appending node={node}, title={title}, icon={icon}, bgcolor={bgcolor}, fgcolor={fgcolor}, icon_open={icon_open}, column count={self.get_n_columns()}")
        self.row_has_child_toggled((index,), rowref)

    def _on_node_changed(self, actions):
        nodes = [a[1] for a in actions if a[0] in ("changed", "changed-recurse")]
        self.emit("node-changed-start", nodes)

        for action in actions:
            act = action[0]
            node = action[1] if act in ("changed", "changed-recurse", "added") else None

            if node and node == self._master_node:
                self.set_root_nodes(self._master_node.get_children())
            elif act == "changed-recurse":
                try:
                    path = get_path_from_node(self, node, self.get_node_column_pos())
                except:
                    continue
                self.remove(self.get_iter(path))
                rowref = self.append(None, [node])
                self.row_has_child_toggled(path, rowref)
            elif act == "added":
                try:
                    path = get_path_from_node(self, node, self.get_node_column_pos())
                except:
                    continue
                rowref = self.append(None, [node])
                parent = node.get_parent()
                if len(parent.get_children()) == 1:
                    parent_path = get_path_from_node(self, parent, self.get_node_column_pos())
                    rowref2 = self.get_iter(parent_path)
                    self.row_has_child_toggled(parent_path, rowref2)
                self.row_has_child_toggled(path, rowref)
            elif act == "act":
                parent = action[1]
                index = action[2]
                try:
                    parent_path = get_path_from_node(self, parent, self.get_node_column_pos())
                except:
                    continue
                path = parent_path + (index,)
                self.remove(self.get_iter(path))
                rowref = self.get_iter(parent_path)
                if len(parent.get_children()) == 0:
                    self.row_has_child_toggled(parent_path, rowref)

        self.emit("node-changed-end", nodes)

    def on_get_iter(self, path):
        try:
            return self.get_iter(path)
        except ValueError:
            return None

    def on_get_path(self, node):
        return get_path_from_node(self, node, self.get_node_column_pos())

    def on_get_value(self, rowref, column):
        print(f"on_get_value: rowref={rowref}, requested column={column}, total columns={self.get_n_columns()}")
        if column >= self.get_n_columns():
            print(f"Error: Column {column} exceeds defined columns {self.get_n_columns()}")
            return None
        node = self.get_value(rowref, 0)
        col = self.get_column(column)
        if col is None:
            print(f"Error: No column definition for index {column}")
            return None
        value = col.get_value(node)
        print(f"Returning value={value} for column={column}")
        return value

GObject.type_register(BaseTreeModel)
GObject.signal_new("node-changed-start", BaseTreeModel, GObject.SignalFlags.RUN_LAST, None, (object,))
GObject.signal_new("node-changed-end", BaseTreeModel, GObject.SignalFlags.RUN_LAST, None, (object,))

class KeepNoteTreeModel(BaseTreeModel):
    def __init__(self, notebook=None):
        super().__init__()
        self._notebook = notebook
        if notebook:
            self.set_root_nodes([notebook])

    def _add_model_column(self, name):
        if name not in self._columns_lookup:
            col = TreeModelColumn(name, None, get=lambda node: None)
            self._columns.append(col)
            self._columns_lookup[name] = col
            col.pos = self.get_column_pos(name)
        return self._columns_lookup[name]

    def get_column_pos(self, name):
        mapping = {
            "node": 0,
            "title": 1,
            "icon": 2,
            "bgcolor": 3,
            "fgcolor": 4,
            "icon_open": 5
        }
        return mapping.get(name, -1)
