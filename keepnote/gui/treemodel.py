# PyGObject imports
from gi import require_version
require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject

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
    """
    TreeModel that wraps a subset of a NoteBook
    The subset is defined by the self._roots list.
    """
    def __init__(self, roots=[]):
        super().__init__(object)  # 直接调用 Gtk.TreeStore 的 __init__，设置列类型为 object

        self._notebook = None
        self._roots = []
        self._root_set = {}
        self._master_node = None
        self._nested = True

        self._columns = []
        self._columns_lookup = {}
        self._node_column = None

        self.set_root_nodes(roots)

        # Add default node column
        self.append_column(TreeModelColumn("node", object, get=lambda node: node))
        self.set_node_column(self.get_column_by_name("node"))

    def set_notebook(self, notebook):
        """
        Set the notebook for this model
        A notebook must be set before any nodes can be added to the model
        """
        if self._notebook is not None:
            self._notebook.node_changed.remove(self._on_node_changed)

        self._notebook = notebook

        if self._notebook:
            self._notebook.node_changed.add(self._on_node_changed)

    # Column manipulation
    def append_column(self, column):
        """Append a new column to the treemodel"""
        assert column.name not in self._columns_lookup
        column.pos = len(self._columns)
        self._columns.append(column)
        self._columns_lookup[column.name] = column

    def get_column(self, pos):
        """Returns a column from a particular position"""
        return self._columns[pos]

    def get_columns(self):
        """Returns list of columns in treemodel"""
        return self._columns

    def get_column_by_name(self, colname):
        """Returns a column with the given name"""
        return self._columns_lookup.get(colname, None)

    def add_column(self, name, coltype, get):
        """Append column only if it does not already exist"""
        col = self.get_column_by_name(name)
        if col is None:
            col = TreeModelColumn(name, coltype, get=get)
            self.append_column(col)
        return col

    def get_node_column_pos(self):
        """Returns the column position containing node objects"""
        assert self._node_column is not None
        return self._node_column.pos

    def get_node_column(self):
        """Returns the column that contains nodes"""
        return self._node_column

    def set_node_column(self, col):
        """Set the column that contains nodes"""
        self._node_column = col

    # Master nodes and root nodes
    def set_master_node(self, node):
        self._master_node = node

    def get_master_node(self):
        return self._master_node

    def set_nested(self, nested):
        """Sets the 'nested mode' of the treemodel"""
        self._nested = nested
        self.set_root_nodes(self._roots)

    def get_nested(self):
        """Returns True if treemodel is in 'nested mode'"""
        return self._nested

    def clear(self):
        super().clear()  # 使用 TreeStore 的 clear 方法
        self._roots = []
        self._root_set = {}

    def set_root_nodes(self, roots=[]):
        """Set the root nodes of the model"""
        self.clear()
        for node in roots:
            self.append(node)
        if len(roots) > 0:
            assert self._notebook is not None

    def get_root_nodes(self):
        """Returns the root nodes of the treemodel"""
        return self._roots

    def append(self, node):
        """Appends a node at the root level of the treemodel"""
        index = len(self._roots)
        self._root_set[node] = index
        self._roots.append(node)
        rowref = super().append(None, [node])  # 使用 TreeStore 的 append
        self.row_has_child_toggled((index,), rowref)

    # Notebook callbacks
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
                self.remove(self.get_iter(path))  # 删除旧节点
                rowref = self.append(None, [node])  # 插入新节点
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

    # 可选：保留部分自定义方法
    def on_get_iter(self, path):
        try:
            return self.get_iter(path)
        except ValueError:
            return None

    def on_get_path(self, node):
        return get_path_from_node(self, node, self.get_node_column_pos())

    def on_get_value(self, rowref, column):
        return self.get_column(column).get_value(self.get_value(rowref, 0))

GObject.type_register(BaseTreeModel)
GObject.signal_new("node-changed-start", BaseTreeModel, GObject.SignalFlags.RUN_LAST, None, (object,))
GObject.signal_new("node-changed-end", BaseTreeModel, GObject.SignalFlags.RUN_LAST, None, (object,))

class KeepNoteTreeModel(BaseTreeModel):
    """
    TreeModel that wraps a subset of a NoteBook
    The subset is defined by the self._roots list.
    """
    def __init__(self, roots=[]):
        super().__init__(roots)
        self.fades = set()