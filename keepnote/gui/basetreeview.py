"""
    KeepNote
    base class for treeview
"""

# python imports
import urllib.parse
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject
from gi.repository import GdkPixbuf
# keepnote.py imports
import keepnote
from keepnote.util.platform import unicode_gtk
from keepnote.notebook import NoteBookError
from keepnote.gui.icons import get_node_icon
from keepnote.gui.treemodel import (
    get_path_from_node, iter_children
)
from keepnote.gui import treemodel, CLIPBOARD_NAME
from keepnote.timestamp import get_str_timestamp

_ = keepnote.translate

MIME_NODE_COPY = "application/x-keepnote.py-node-copy"
MIME_TREE_COPY = "application/x-keepnote.py-tree-copy"
MIME_NODE_CUT = "application/x-keepnote.py-node-cut"

# treeview drag and drop config
DROP_URI = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
DROP_TREE_MOVE = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)

# treeview reorder rules
REORDER_NONE = 0
REORDER_FOLDER = 1
REORDER_ALL = 2

def parse_utf(text):
    if (text[:2] in (b'\xff\xfe', b'\xfe\xff') or
            (len(text) > 1 and text[1] == 0) or
            (len(text) > 3 and text[3] == 0)):
        return text.decode("utf-16")
    else:
        text = text.replace(b"\x00", b"")
        return text.decode("utf-8")

def compute_new_path(model, target, drop_position):
    path = model.get_path(target)
    if drop_position in (Gtk.TreeViewDropPosition.INTO_OR_BEFORE, Gtk.TreeViewDropPosition.INTO_OR_AFTER):
        return path + (0,)
    elif drop_position == Gtk.TreeViewDropPosition.BEFORE:
        return path
    elif drop_position == Gtk.TreeViewDropPosition.AFTER:
        return path[:-1] + (path[-1] + 1,)
    else:
        raise Exception("unknown drop position %s" % str(drop_position))

class TextRendererValidator:
    def __init__(self, format=lambda x: x, parse=lambda x: x, validate=lambda x: True):
        def parse2(x):
            if not validate(x):
                raise Exception("Invalid")
            return parse(x)
        self.format = format
        self.parse = parse2

class KeepNoteBaseTreeView(Gtk.TreeView):
    def __init__(self):
        super().__init__()

        self.model = None
        self.rich_model = None
        self._notebook = None
        self._master_node = None
        self.editing_path = False
        self.__sel_nodes = []
        self.__sel_nodes2 = []
        self.__scroll = (0, 0)
        self.__suppress_sel = False
        self._node_col = None
        self._get_icon = None
        self._get_node = self._get_node_default
        self._date_formats = {}

        self.changed_start_id = None
        self.changed_end_id = None
        self.insert_id = None
        self.delete_id = None
        self.has_child_id = None

        self._menu = None

        self._attr_title = "title"
        self._attr_icon = "icon"
        self._attr_icon_open = "icon_open"

        self.get_selection().connect("changed", self.__on_select_changed)
        self.get_selection().connect("changed", self.on_select_changed)

        self.connect("row-expanded", self._on_row_expanded)
        self.connect("row-collapsed", self._on_row_collapsed)

        self._is_dragging = False
        self._drag_count = 0
        self._dest_row = None
        self._reorder = REORDER_ALL
        self._drag_scroll_region = 30

        self.connect("copy-clipboard", self._on_copy_node)
        self.connect("copy-tree-clipboard", self._on_copy_tree)
        self.connect("cut-clipboard", self._on_cut_node)
        self.connect("paste-clipboard", self._on_paste_node)

        drag_source = Gtk.DragSource.new()
        drag_source.set_actions(Gdk.DragAction.MOVE)
        drag_source.connect("prepare", self._on_drag_prepare)
        drag_source.connect("drag-begin", self._on_drag_begin)
        drag_source.connect("drag-end", self._on_drag_end)
        self.add_controller(drag_source)

        drop_target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE | Gdk.DragAction.COPY)
        drop_target.connect("motion", self._on_drag_motion)
        drop_target.connect("drop", self._on_drag_drop)
        self.add_controller(drop_target)

    def set_master_node(self, node):
        self._master_node = node
        if self.rich_model:
            self.rich_model.set_master_node(node)

    def get_master_node(self):
        return self._master_node

    def set_notebook(self, notebook):
        self._notebook = notebook
        if self.model:
            if hasattr(self.model, "get_model"):
                self.model.get_model().set_notebook(notebook)
            else:
                self.model.set_notebook(notebook)

    def set_get_node(self, get_node_func=None):
        if get_node_func is None:
            self._get_node = self._get_node_default
        else:
            self._get_node = get_node_func

    def _get_node_default(self, nodeid):
        if self._notebook is None:
            return None
        return self._notebook.get_node_by_id(nodeid)

    def set_model(self, model):
        if self.model is not None and self.rich_model is not None:
            if self.changed_start_id is not None:
                self.rich_model.disconnect(self.changed_start_id)
            if self.changed_end_id is not None:
                self.rich_model.disconnect(self.changed_end_id)
            if self.insert_id is not None:
                self.model.disconnect(self.insert_id)
            if self.delete_id is not None:
                self.model.disconnect(self.delete_id)
            if self.has_child_id is not None:
                self.model.disconnect(self.has_child_id)

            self._node_col = None
            self._get_icon = None

        self.model = model
        self.rich_model = None
        super().set_model(self.model)

        if self.model is not None:
            if hasattr(self.model, "get_model"):
                self.rich_model = self.model.get_model()
            else:
                self.rich_model = model

            self.rich_model.set_notebook(self._notebook)
            self.changed_start_id = self.rich_model.connect("node-changed-start", self._on_node_changed_start)
            self.changed_end_id = self.rich_model.connect("node-changed-end", self._on_node_changed_end)
            self._node_col = self.rich_model.get_node_column_pos()
            self._get_icon = lambda row: self.model.get_value(row, self.rich_model.get_column_by_name("icon").pos)

            self.insert_id = self.model.connect("row-inserted", self.on_row_inserted)
            self.delete_id = self.model.connect("row-deleted", self.on_row_deleted)
            self.has_child_id = self.model.connect("row-has-child-toggled", self.on_row_has_child_toggled)

    def set_popup_menu(self, menu):
        self._menu = menu

    def get_popup_menu(self):
        return self._menu

    def popup_menu(self, x, y, button, time):
        if self._menu is None:
            return
        path = self.get_path_at_pos(int(x), int(y))
        if path is None:
            return False
        path = path[0]
        if not self.get_selection().path_is_selected(path):
            self.get_selection().unselect_all()
            self.get_selection().select_path(path)
        popup = Gtk.PopoverMenu.new_from_model(self._menu)
        popup.set_parent(self)
        popup.set_position(Gtk.PositionType.BOTTOM)
        popup.popup()
        return True

    def clear_columns(self):
        for col in reversed(self.get_columns()):
            self.remove_column(col)

    def get_column_by_attr(self, attr):
        for col in self.get_columns():
            if col.attr == attr:
                return col
        return None

    def _add_title_render(self, column, attr):
        self._add_model_column(self._attr_icon)
        self._add_model_column(self._attr_icon_open)

        cell_icon = self._add_pixbuf_render(column, self._attr_icon, self._attr_icon_open)
        title_text = self._add_text_render(column, attr, editable=True,
                                           validator=TextRendererValidator(validate=lambda x: x != ""))
        self.title_text = title_text
        return cell_icon, title_text

    def _add_text_render(self, column, attr, editable=False, validator=TextRendererValidator()):
        cell = Gtk.CellRendererText()
        cell.set_fixed_height_from_font(1)
        column.pack_start(cell, True)
        column.add_attribute(cell, 'text', self.rich_model.get_column_by_name(attr).pos)
        column.add_attribute(cell, 'cell-background', self.rich_model.add_column("title_bgcolor", str, lambda node: node.get_attr("title_bgcolor", None)).pos)
        column.add_attribute(cell, 'foreground', self.rich_model.add_column("title_fgcolor", str, lambda node: node.get_attr("title_fgcolor", None)).pos)

        if editable:
            cell.connect("edited", lambda r, p, t: self.on_edit_attr(r, p, attr, t, validator=validator))
            cell.connect("editing-started", lambda r, e, p: self.on_editing_started(r, e, p, attr, validator))
            cell.connect("editing-canceled", self.on_editing_canceled)
            cell.set_property("editable", True)
        return cell

    def _add_pixbuf_render(self, column, attr, attr_open=None):
        cell = Gtk.CellRendererPixbuf()
        column.pack_start(cell, False)
        column.add_attribute(cell, 'pixbuf', self.rich_model.get_column_by_name(attr).pos)
        if attr_open:
            column.add_attribute(cell, 'pixbuf-expander-open', self.rich_model.get_column_by_name(attr_open).pos)
        return cell

    def _get_model_column(self, attr, mapfunc=lambda x: x):
        col = self.rich_model.get_column_by_name(attr)
        if col is None:
            self._add_model_column(attr, add_sort=False, mapfunc=mapfunc)
            col = self.rich_model.get_column_by_name(attr)
        return col

    def get_col_type(self, datatype):
        if datatype == "string":
            return str
        elif datatype == "integer":
            return int
        elif datatype == "float":
            return float
        elif datatype == "timestamp":
            return str
        else:
            return str

    def get_col_mapfunc(self, datatype):
        if datatype == "timestamp":
            return self.format_timestamp
        else:
            return lambda x: x

    def _add_model_column(self, attr, add_sort=True, mapfunc=lambda x: x):
        attr_def = self._notebook.attr_defs.get(attr)
        if attr_def is not None:
            datatype = attr_def.datatype
            default = attr_def.default
        else:
            datatype = "string"
            default = ""

        get = lambda node: mapfunc(node.get_attr(attr, default))
        mapfunc_sort = lambda x: x
        if datatype == "string":
            coltype = str
            coltype_sort = str
            mapfunc_sort = lambda x: x.lower()
        elif datatype == "integer":
            coltype = int
            coltype_sort = int
        elif datatype == "float":
            coltype = float
            coltype_sort = float
        elif datatype == "timestamp":
            mapfunc = self.format_timestamp
            coltype = str
            coltype_sort = int
        else:
            coltype = str
            coltype_sort = str

        if attr == self._attr_icon:
            coltype = GdkPixbuf.Pixbuf
            coltype_sort = None
            get = lambda node: get_node_icon(node, False, node in self.rich_model.fades)
        elif attr == self._attr_icon_open:
            coltype = GdkPixbuf.Pixbuf
            coltype_sort = None
            get = lambda node: get_node_icon(node, True, node in self.rich_model.fades)

        col = self.rich_model.get_column_by_name(attr)
        if col is None:
            col = treemodel.TreeModelColumn(attr, coltype, attr=attr, get=get)
            self.rich_model.append_column(col)

        if add_sort and coltype_sort is not None:
            attr_sort = attr + "_sort"
            col = self.rich_model.get_column_by_name(attr_sort)
            if col is None:
                get_sort = lambda node: mapfunc_sort(node.get_attr(attr, default))
                col = treemodel.TreeModelColumn(attr_sort, coltype_sort, attr=attr, get=get_sort)
                self.rich_model.append_column(col)

    def set_date_formats(self, formats):
        self._date_formats = formats

    def format_timestamp(self, timestamp):
        return (get_str_timestamp(timestamp, formats=self._date_formats) if timestamp is not None else "")

    def _on_node_changed_start(self, model, nodes):
        self.__sel_nodes2 = list(self.__sel_nodes)
        self.__suppress_sel = True
        self.cancel_editing()
        self.__scroll = self.convert_widget_to_tree_coords(0, 0)

    def _on_node_changed_end(self, model, nodes):
        for node in nodes:
            if node == self._master_node:
                for child in node.get_children():
                    if self.is_node_expanded(child):
                        path_tuple = get_path_from_node(self.model, child, self.rich_model.get_node_column_pos())
                        path = Gtk.TreePath.new_from_indices(path_tuple)
                        self.expand_row(path, False)
            else:
                try:
                    path_tuple = get_path_from_node(self.model, node, self.rich_model.get_node_column_pos())
                    path = Gtk.TreePath.new_from_indices(path_tuple)
                except:
                    path = None
                if path is not None:
                    parent = node.get_parent()
                    if parent and self.is_node_expanded(parent) and len(path) > 1:
                        self.expand_row(path[:-1], False)
                    if self.is_node_expanded(node):
                        self.expand_row(path, False)

    def __on_select_changed(self, treeselect):
        self.__sel_nodes = self.get_selected_nodes()
        if self.__suppress_sel:
            self.get_selection().stop_emission("changed")

    def is_node_expanded(self, node):
        return node.get_attr("expanded", False)

    def set_node_expanded(self, node, expand):
        node.set_attr("expanded", expand)

    def _on_row_expanded(self, treeview, it, path):
        self.set_node_expanded(self.model.get_value(it, self._node_col), True)
        def walk(it):
            child = self.model.iter_children(it)
            while child:
                node = self.model.get_value(child, self._node_col)
                if self.is_node_expanded(node):
                    path = self.model.get_path(child)
                    self.expand_row(path, False)
                    walk(child)
                child = self.model.iter_next(child)
        walk(it)

    def _on_row_collapsed(self, treeview, it, path):
        self.set_node_expanded(self.model.get_value(it, self._node_col), False)

    def on_row_inserted(self, model, path, it):
        pass

    def on_row_deleted(self, model, path):
        pass

    def on_row_has_child_toggled(self, model, path, it):
        pass

    def cancel_editing(self):
        if self.editing_path:
            self.set_cursor(self.editing_path, None, False)

    def expand_node(self, node):
        path = get_path_from_node(self.model, node, self.rich_model.get_node_column_pos())
        if path is not None:
            self.expand_to_path(path)

    def collapse_all_beneath(self, path):
        it = self.model.get_iter(path)
        def walk(it):
            for child in iter_children(self.model, it):
                walk(child)
            path2 = self.model.get_path(it)
            self.collapse_row(path2)
        walk(it)

    def select_nodes(self, nodes):
        if len(nodes) > 0:
            node = nodes[0]
            path = get_path_from_node(self.model, node, self.rich_model.get_node_column_pos())
            if path is not None:
                if len(path) > 1:
                    self.expand_to_path(path[:-1])
                self.set_cursor(path)
                GObject.idle_add(lambda: self.scroll_to_cell(path))
        else:
            self.get_selection().unselect_all()

    def on_select_changed(self, treeselect):
        nodes = self.get_selected_nodes()
        self.emit("select-nodes", nodes)
        return True

    def get_selected_nodes(self):
        iters = self.get_selected_iters()
        if len(iters) == 0:
            if self.editing_path:
                node = self._get_node_from_path(self.editing_path)
                if node:
                    return [node]
            return []
        return [self.model.get_value(it, self._node_col) for it in iters]

    def get_selected_iters(self):
        iters = []
        self.get_selection().selected_foreach(lambda model, path, it: iters.append(it))
        return iters

    def on_editing_started(self, cellrenderer, editable, path, attr, validator=TextRendererValidator()):
        self.editing_path = path
        node = self.model.get_value(self.model.get_iter(path), self._node_col)
        if node is not None:
            val = node.get_attr(attr)
            try:
                editable.set_text(validator.format(val))
            except:
                pass
        GObject.idle_add(lambda: self.scroll_to_cell(path))

    def on_editing_canceled(self, cellrenderer):
        self.editing_path = None

    def on_edit_attr(self, cellrenderertext, path, attr, new_text, validator=TextRendererValidator()):
        self.editing_path = None
        new_text = unicode_gtk(new_text)
        node = self.model.get_value(self.model.get_iter(path), self._node_col)
        if node is None:
            return
        try:
            new_val = validator.parse(new_text)
        except:
            return
        try:
            node.set_attr(attr, new_val)
        except NoteBookError as e:
            self.emit("error", e.msg, e)
        path = get_path_from_node(self.model, node, self.rich_model.get_node_column_pos())
        if path is not None:
            self.set_cursor(path)
            GObject.idle_add(lambda: self.scroll_to_cell(path))
        self.emit("edit-node", node, attr, new_val)

    def _on_copy_node(self, widget):
        nodes = self.get_selected_nodes()
        if len(nodes) > 0:
            clipboard = Gtk.Clipboard.get_default(self.get_display())
            content = Gdk.ContentProvider.new_for_value(GObject.Value(str, ";".join([node.get_attr("nodeid") for node in nodes])))
            clipboard.set_content(content)

    def _on_copy_tree(self, widget):
        nodes = self.get_selected_nodes()
        if len(nodes) > 0:
            clipboard = Gtk.Clipboard.get_default(self.get_display())
            content = Gdk.ContentProvider.new_for_value(GObject.Value(str, ";".join([node.get_attr("nodeid") for node in nodes])))
            clipboard.set_content(content)

    def _on_cut_node(self, widget):
        nodes = self.get_selected_nodes()
        if len(nodes) > 0:
            clipboard = Gtk.Clipboard.get_default(self.get_display())
            content = Gdk.ContentProvider.new_for_value(GObject.Value(str, ";".join([node.get_attr("nodeid") for node in nodes])))
            clipboard.set_content(content)
            self._fade_nodes(nodes)

    def _on_paste_node(self, widget):
        clipboard = Gtk.Clipboard.get_default(self.get_display())
        clipboard.read_value_async(GObject.TYPE_STRING, 0, None, self._do_paste_nodes)

    def _do_paste_nodes(self, clipboard, result, data):
        if self._notebook is None:
            return
        selected = self.get_selected_nodes()
        parent = selected[0] if len(selected) > 0 else self._notebook
        try:
            value = clipboard.read_value_finish(result)
            nodeids = value.split(";")
            nodes = [self._get_node(nodeid) for nodeid in nodeids]
            for node in nodes:
                if node is not None:
                    node.move(parent)
        except Exception as e:
            keepnote.log_error(e)

    def _clear_fading(self):
        nodes = list(self.rich_model.fades)
        self.rich_model.fades.clear()
        if self._notebook:
            self._notebook.notify_changes(nodes, False)

    def _fade_nodes(self, nodes):
        self.rich_model.fades.clear()
        for node in nodes:
            self.rich_model.fades.add(node)
            node.notify_change(False)

    def set_reorder(self, order):
        self._reorder = order

    def get_reorderable(self):
        return self._reorder

    def get_drag_node(self):
        iters = self.get_selected_iters()
        if len(iters) == 0:
            return None
        return self.model.get_value(iters[0], self._node_col)

    def get_drag_nodes(self):
        return [self.model.get_value(it, self._node_col) for it in self.get_selected_iters()]

    def _on_drag_timer(self):
        self._process_drag_scroll()
        return self._is_dragging

    def _process_drag_scroll(self):
        header_height = 0
        if self.get_headers_visible():
            header_height = self.get_column(0).get_area().height
        x, y = self.get_pointer()
        x, y = self.convert_widget_to_tree_coords(x, y - header_height)
        rect = self.get_visible_rect()
        def dist_to_scroll(dist):
            small_scroll_dist = 30
            small_scroll = 30
            fast_scroll_coeff = small_scroll
            if dist < small_scroll_dist:
                self._drag_count = 0
                return small_scroll
            else:
                self._drag_count += 1
                return small_scroll + fast_scroll_coeff * self._drag_count**2
        dist = rect.y - y
        if dist > 0:
            self.scroll_to_point(-1, rect.y - dist_to_scroll(dist))
        else:
            dist = y - rect.y - rect.height
            if dist > 0:
                self.scroll_to_point(-1, rect.y + dist_to_scroll(dist))

    def _on_drag_prepare(self, source, x, y):
        iters = self.get_selected_iters()
        if len(iters) == 0:
            return None
        source_path = self.model.get_path(iters[0])
        return Gdk.ContentProvider.new_for_value(GObject.Value(str, str(source_path)))

    def _on_drag_begin(self, source, drag):
        iters = self.get_selected_iters()
        if len(iters) == 0:
            return
        source = iters[0]
        if self._get_icon:
            pixbuf = self._get_icon(source)
            pixbuf = pixbuf.scale_simple(40, 40, GdkPixbuf.InterpType.BILINEAR)
            drag.set_icon(Gdk.Texture.new_for_pixbuf(pixbuf), 0, 0)
        self._dest_row = None
        self.cancel_editing()
        self._is_dragging = True
        self._drag_count = 0
        GObject.timeout_add(200, self._on_drag_timer)

    def _on_drag_motion(self, target, x, y, data):
        if self._reorder == REORDER_NONE:
            return Gdk.DragAction(0)
        dest_row = self.get_dest_row_at_pos(x, y)
        if dest_row is not None:
            target_path, drop_position = dest_row
            target = self.model.get_iter(target_path)
            target_node = self.model.get_value(target, self._node_col)
            self.set_drag_dest_row(target_path, drop_position)
            self._dest_row = (target_path, drop_position)
            return Gdk.DragAction.MOVE
        return Gdk.DragAction(0)

    def _on_drag_drop(self, target, value, x, y):
        if self._reorder == REORDER_NONE:
            return False
        if self._dest_row is None:
            return False
        target_path, drop_position = self._dest_row
        target = self.model.get_iter(target_path)
        target_node = self.model.get_value(target, self._node_col)
        new_path = compute_new_path(self.model, target, drop_position)
        new_parent = self._get_node_from_path(new_path[:-1])
        index = new_path[-1]
        source_path = Gtk.TreePath.new_from_string(value)
        source = self.model.get_iter(source_path)
        source_node = self.model.get_value(source, self._node_col)
        if not self._drop_allowed(source_node, target_node, drop_position):
            return False
        try:
            source_node.move(new_parent, index)
            self.emit("goto-node", source_node)
            return True
        except NoteBookError as e:
            self.emit("error", e.msg, e)
            return False

    def _on_drag_end(self, source, drag, delete):
        self._is_dragging = False

    def _get_node_from_path(self, path):
        if len(path) == 0:
            assert self._master_node is not None
            return self._master_node
        else:
            it = self.model.get_iter(path)
            return self.model.get_value(it, self._node_col)

    def _drop_allowed(self, source_node, target_node, drop_position):
        ptr = target_node
        while ptr is not None:
            if ptr == source_node:
                return False
            ptr = ptr.get_parent()
        drop_into = (drop_position == Gtk.TreeViewDropPosition.INTO_OR_BEFORE or
                     drop_position == Gtk.TreeViewDropPosition.INTO_OR_AFTER)
        return (
            not (target_node.get_parent() is None and not drop_into) and
            not (not target_node.allows_children() and drop_into) and
            not (source_node and self._reorder == REORDER_FOLDER and not drop_into and
                 target_node.get_parent() == source_node.get_parent())
        )

GObject.type_register(KeepNoteBaseTreeView)
GObject.signal_new("goto-node", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, (object,))
GObject.signal_new("activate-node", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, (object,))
GObject.signal_new("delete-node", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, (object,))
GObject.signal_new("goto-parent-node", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, ())
GObject.signal_new("copy-clipboard", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, ())
GObject.signal_new("copy-tree-clipboard", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, ())
GObject.signal_new("cut-clipboard", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, ())
GObject.signal_new("paste-clipboard", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, ())
GObject.signal_new("select-nodes", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, (object,))
GObject.signal_new("edit-node", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, (object, str, str))
GObject.signal_new("drop-file", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, (object, int, str))
GObject.signal_new("error", KeepNoteBaseTreeView, GObject.SignalFlags.RUN_LAST, None, (str, object,))