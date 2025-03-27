# KeepNote
# Copyright (c) 2008-2009 Matt Rasmussen
# Author: Matt Rasmussen <rasmus@alum.mit.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.

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

    # Determine root set
    root_set = {}
    child = model.iter_children(None)
    i = 0
    while child is not None:
        root_set[model.get_value(child, node_col)] = i
        child = model.iter_next(child)
        i += 1

    # Walk up parent path until root set
    node_path = []
    while node not in root_set:
        node_path.append(node)
        node = node.get_parent()
        if node is None:
            return None  # Node is not in the model

    # Walk back down and record path
    path = [root_set[node]]
    it = model.get_iter(tuple(path))
    for node in reversed(node_path):
        child = model.iter_children(it)
        i = 0
        while child is not None:
            if model.get_value(child, node_col) == node:
                path.append(i)
                it = child
                break
            child = model.iter_next(child)
            i += 1
        else:
            raise Exception("bad model")

    return tuple(path)


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


class BaseTreeModel(GObject.Object, Gtk.TreeModel):
    """
    TreeModel that wraps a subset of a NoteBook

    The subset is defined by the self._roots list.
    """

    def __init__(self, roots=[]):
        GObject.Object.__init__(self)
        self.set_property("leak-references", False)

        self._notebook = None
        self._roots = []
        self._root_set = {}  # Added to initialize properly
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
        """Clear all rows from model"""
        for i in range(len(self._roots) - 1, -1, -1):
            self.row_deleted((i,))
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
        rowref = self.create_tree_iter(node)
        self.row_inserted((index,), rowref)
        self.row_has_child_toggled((index,), rowref)
        self.row_has_child_toggled((index,), rowref)  # Double call preserved from original

    # Notebook callbacks
    def _on_node_changed(self, actions):
        """Callback for when a node changes"""
        nodes = [a[1] for a in actions if a[0] in ("changed", "changed-recurse")]
        self.emit("node-changed-start", nodes)

        for action in actions:
            act = action[0]
            node = action[1] if act in ("changed", "changed-recurse", "added") else None

            if node and node == self._master_node:
                self.set_root_nodes(self._master_node.get_children())
            elif act == "changed-recurse":
                try:
                    path = self.on_get_path(node)
                except:
                    continue
                rowref = self.create_tree_iter(node)
                self.row_deleted(path)
                self.row_inserted(path, rowref)
                self.row_has_child_toggled(path, rowref)
            elif act == "added":
                try:
                    path = self.on_get_path(node)
                except:
                    continue
                rowref = self.create_tree_iter(node)
                self.row_inserted(path, rowref)
                parent = node.get_parent()
                if len(parent.get_children()) == 1:
                    rowref2 = self.create_tree_iter(parent)
                    self.row_has_child_toggled(path[:-1], rowref2)
                self.row_has_child_toggled(path, rowref)
            elif act == "removed":
                parent = action[1]
                index = action[2]
                try:
                    parent_path = self.on_get_path(parent)
                except:
                    continue
                path = parent_path + (index,)
                self.row_deleted(path)
                rowref = self.create_tree_iter(parent)
                if len(parent.get_children()) == 0:
                    self.row_has_child_toggled(parent_path, rowref)

        self.emit("node-changed-end", nodes)

    # Gtk.GenericTreeModel implementation
    def on_get_flags(self):
        """Returns the flags of this treemodel"""
        return Gtk.TreeModelFlags.ITERS_PERSIST

    def on_get_n_columns(self):
        """Returns the number of columns in a treemodel"""
        return len(self._columns)

    def on_get_column_type(self, index):
        """Returns the type of a column in the treemodel"""
        return self._columns[index].type

    def on_get_iter(self, path):
        """Returns the node of a path"""
        if path[0] >= len(self._roots):
            return None
        node = self._roots[path[0]]
        for i in path[1:]:
            children = node.get_children()
            if i >= len(children):
                raise ValueError()
            node = children[i]
        return node

    def on_get_path(self, rowref):
        """Returns the path of a rowref"""
        if rowref is None:
            return ()
        path = []
        node = rowref
        while node not in self._root_set:
            path.append(node.get_attr("order"))
            node = node.get_parent()
            if node is None:
                raise Exception("treeiter is not part of model")
        path.append(self._root_set[node])
        return tuple(reversed(path))

    def on_get_value(self, rowref, column):
        """Returns a value from a row in the treemodel"""
        return self.get_column(column).get_value(rowref)

    def on_iter_next(self, rowref):
        """Returns the next sibling of a rowref"""
        parent = rowref.get_parent()
        if parent is None or rowref in self._root_set:
            n = self._root_set[rowref]
            return self._roots[n + 1] if n < len(self._roots) - 1 else None
        children = parent.get_children()
        order = rowref.get_attr("order")
        assert 0 <= order < len(children)
        return children[order + 1] if order < len(children) - 1 else None

    def on_iter_children(self, parent):
        """Returns the first child of a treeiter"""
        if parent is None:
            return self._roots[0] if self._roots else None
        return parent.get_children()[0] if self._nested and parent.get_children() else None

    def on_iter_has_child(self, rowref):
        """Returns True if treeiter has children"""
        return self._nested and rowref.has_children()

    def on_iter_n_children(self, rowref):
        """Returns the number of children of a treeiter"""
        if rowref is None:
            return len(self._roots)
        return len(rowref.get_children()) if self._nested else 0

    def on_iter_nth_child(self, parent, n):
        """Returns the n'th child of a treeiter"""
        if parent is None:
            return self._roots[n] if n < len(self._roots) else None
        if not self._nested:
            return None
        children = parent.get_children()
        return children[n] if n < len(children) else None

    def on_iter_parent(self, child):
        """Returns the parent of a treeiter"""
        return None if child in self._root_set else child.get_parent()


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
        # Note: Commented-out column initialization moved to treeviewer as per original comment