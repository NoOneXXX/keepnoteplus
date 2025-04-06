# PyGObject imports
from gi import require_version

require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk, Gdk
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

# KeepNote imports
from keepnote.gui import basetreeview
from keepnote.gui import treemodel
import keepnote
import keepnote.timestamp

_ = keepnote.translate

DEFAULT_ATTR_COL_WIDTH = 150
DEFAULT_TITLE_COL_WIDTH = 250


class KeepNoteListView(basetreeview.KeepNoteBaseTreeView):

    def __init__(self):
        super().__init__()
        self._sel_nodes = None
        self._columns_set = False
        self._current_table = "default"
        self._col_widths = {}
        self.time_edit_format = "%Y/%m/%d %H:%M:%S"

        # Configurable callback for setting window status
        self.on_status = None

        # Selection config
        self.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        # Init view
        #
        controller = Gtk.EventControllerKey()
        controller.connect("key-released", self.on_key_released)
        self.add_controller(controller)
        controller = Gtk.EventControllerKey()
        controller.connect("key-released", self.on_key_released)
        self.add_controller(controller)

        gesture = Gtk.GestureClick()
        gesture.connect("pressed", self.on_button_press)
        self.add_controller(gesture)
        self.connect("row-expanded", self._on_listview_row_expanded)
        self.connect("row-collapsed", self._on_listview_row_collapsed)
        self.connect("notify::columns", self._on_columns_changed)

# GTK4 不再支持 set_enable_tree_lines / Gtk.TreeViewLines
# 如需类似效果，可使用 CSS 设置网格线，如 grid-lines: both;
        self.set_fixed_height_mode(True)
        self.set_sensitive(False)

        # Init model
        self.set_model(Gtk.TreeModelSort.new_with_model(treemodel.KeepNoteTreeModel()))

        self.setup_columns()

    def load_preferences(self, app_pref, first_open=False):
        """Load application preferences"""

        # 原来的写法有 default 参数，dict 不支持这个
        formats = app_pref.get("timestamp_formats")
        if not formats:
            formats = ["%Y-%m-%d %H:%M:%S"]
        self.set_date_formats(formats)

        # GTK4 不再支持 set_enable_grid_lines，建议用 CSS 设置
        rules_enabled = False
        look_and_feel = app_pref.get("look_and_feel", {})
        if isinstance(look_and_feel, dict):
            rules_enabled = look_and_feel.get("listview_rules", True)

        if rules_enabled:
            # 使用 CSS 设置网格线效果
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(b"""
            treeview cell {
                border-bottom: 1px solid #ccc;
                border-right: 1px solid #ccc;
                padding: 2px;
            }
            """)

            style_context = self.get_style_context()
            style_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def save_preferences(self, app_pref):
        """Save application preferences"""
        pass

    def set_notebook(self, notebook):
        """Set the notebook for listview"""
        if notebook != self._notebook and self._notebook is not None:
            self._notebook.get_listeners("table_changed").remove(
                self._on_table_changed)

        super().set_notebook(notebook)

        if self.rich_model is not None:
            self.rich_model.set_root_nodes([])

        if notebook:
            # Load notebook prefs
            self.set_sensitive(True)
            notebook.get_listeners("table_changed").add(self._on_table_changed)
        else:
            self.set_sensitive(False)

        self.setup_columns()

    def save(self):
        """Save notebook preferences"""
        if self._notebook is None:
            return

        self._save_column_widths()
        self._save_column_order()

        self._notebook.mark_modified()

    def _save_column_widths(self):
        # Save attr column widths
        widths = self._notebook.get_attr("column_widths", {})
        for col in self.get_columns():
            widths[col.attr] = col.get_width()
        self._notebook.set_attr("column_widths", widths)

    def _save_column_order(self):
        # Save column attrs
        table = self._notebook.attr_tables.get(self._current_table)
        table.attrs = [col.attr for col in self.get_columns()]

    def _load_column_widths(self):
        widths = self._notebook.get_attr("column_widths", {})
        for col in self.get_columns():
            width = widths.get(col.attr, DEFAULT_ATTR_COL_WIDTH)
            if col.get_width() != width and width > 0:
                col.set_fixed_width(width)
                widths[col.attr] = width

    def _load_column_order(self):
        current_attrs = [col.attr for col in self.get_columns()]
        table = self._notebook.attr_tables.get(self._current_table)

        if table.attrs != current_attrs:
            if set(current_attrs) == set(table.attrs):
                # Only order changed
                lookup = {col.attr: col for col in self.get_columns()}
                prev = None
                for attr in table.attrs:
                    col = lookup[attr]
                    self.move_column_after(col, prev)
                    prev = col
            else:
                # Resetup all columns
                self.setup_columns()

    def _on_table_changed(self, notebook, table):
        if self._notebook == notebook and table == self._current_table:
            self._load_column_widths()
            self._load_column_order()

    # ==================================
    # Model and view setup

    def set_model(self, model):
        super().set_model(model)
        if model:
            self.model.connect("sort-column-changed", self._sort_column_changed)

    def setup_columns(self):
        self.clear_columns()

        if self._notebook is None:
            self._columns_set = False
            return

        # 获取属性表，确保不为空
        attrs = self._notebook.attr_tables.get(self._current_table)
        if not attrs or not attrs.attrs:
            attrs.attrs = ["title", "created_time"]  # 默认列

        # 添加列
        for attr in attrs.attrs:
            col = self._add_column(attr)
            col.set_reorderable(True)
            if attr == self._attr_title:
                self.title_column = col

        # 添加模型列
        self._add_model_column("order")

        # 创建排序模型
        if self.rich_model is None:
            self.rich_model = treemodel.KeepNoteTreeModel()
        self.set_model(Gtk.TreeModelSort.new_with_model(self.rich_model))

        # 配置列视图
        self.set_expander_column(self.get_column(0))

        # 设置默认排序
        order_col = self.rich_model.get_column_by_name("order")
        if order_col and self.model and self.rich_model.get_n_columns() > 0:
            self.model.set_sort_column_id(order_col.pos, Gtk.SortType.ASCENDING)
        else:
            print("Warning: Skipping sort setup - model not fully initialized")
        self.set_reorder(basetreeview.REORDER_ALL)

        self._columns_set = True

    def _add_column(self, attr, cell_attr=None):
        attr_def = self._notebook.attr_defs.get(attr)
        datatype = attr_def.datatype if attr_def else "string"
        col_title = attr_def.name if attr_def else attr

        # 确保模型列存在
        if not self.rich_model.get_column_by_name(attr):
            self._add_model_column(attr)

        column = Gtk.TreeViewColumn()
        column.attr = attr
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_resizable(True)
        column.connect("notify::width", self._on_column_width_change)
        column.set_min_width(10)
        column.set_fixed_width(
            self._notebook.get_attr("column_widths", {}).get(
                attr, DEFAULT_ATTR_COL_WIDTH))
        column.set_title(col_title)

        # Define column sorting
        attr_sort = attr + "_sort"
        col = self.rich_model.get_column_by_name(attr_sort)
        if col:
            column.set_sort_column_id(col.pos)

        # Add cell renderers
        if attr == self._attr_title:
            self._add_title_render(column, attr)
        elif datatype == "timestamp":
            self._add_text_render(
                column, attr, editable=True,
                validator=basetreeview.TextRendererValidator(
                    lambda x: keepnote.timestamp.format_timestamp(x, self.time_edit_format) if x else "",
                    lambda x: keepnote.timestamp.parse_timestamp(x, self.time_edit_format) if x else 0))
        else:
            self._add_text_render(column, attr)

        self.append_column(column)
        return column

    # =============================================
    # GUI callbacks

    def is_node_expanded(self, node):
        return node.get_attr("expanded2", False)

    def set_node_expanded(self, node, expand):
        if len(treemodel.get_path_from_node(
                self.model, node,
                self.rich_model.get_node_column_pos())) > 1:
            node.set_attr("expanded2", expand)

    def _sort_column_changed(self, sortmodel):
        self._update_reorder()

    def _update_reorder(self):
        col_id, sort_dir = self.model.get_sort_column_id()

        if col_id is None or col_id < 0:
            col = None
        else:
            col = self.rich_model.get_column(col_id)

        if col is None:
            order_col = self.rich_model.get_column_by_name("order")
            if order_col and self.model and self.rich_model.get_n_columns() > 0:
                self.model.set_sort_column_id(order_col.pos, Gtk.SortType.ASCENDING)
                self.set_reorder(basetreeview.REORDER_ALL)
            else:
                print("Warning: Skipping reorder - model not fully initialized")
            self.set_reorder(basetreeview.REORDER_ALL)
        else:
            self.set_reorder(basetreeview.REORDER_FOLDER)

    def on_key_released(self, widget, event):
        """Callback for key release events"""
        if self.editing_path:
            return

        # In GTK 4, event.keyval is replaced with event.get_keyval()[1]
        keyval = event.get_keyval()[1]
        state = event.get_state()[1]  # In GTK 4, get_state() returns a tuple

        if keyval == Gdk.KEY_Delete:
            self.stop_emission("key-release-event")
            self.emit("delete-node", self.get_selected_nodes())

        elif keyval == Gdk.KEY_BackSpace and state & Gdk.ModifierType.CONTROL_MASK:
            self.stop_emission("key-release-event")
            self.emit("goto-parent-node")

        elif keyval == Gdk.KEY_Return and state & Gdk.ModifierType.CONTROL_MASK:
            self.stop_emission("key-release-event")
            self.emit("activate-node", None)

    def on_button_press(self, widget, event):
        if event.button == 3:
            return self.popup_menu(event.x, event.y, event.button, event.time)

        if event.button == 1 and event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:  # Changed from _2BUTTON_PRESS
            model, paths = self.get_selection().get_selected_rows()
            if len(paths) > 0:
                nodes = [
                    self.model.get_value(self.model.get_iter(x),
                                         self.rich_model.get_node_column_pos())
                    for x in paths]
                self.emit("activate-node", nodes[0])

    def is_view_tree(self):
        return self.get_master_node() is not None

    def _on_columns_changed(self, treeview):
        """Callback for when columns change order"""
        if not self._columns_set:
            return

        col = self.get_column(0)
        if col:
            self.set_expander_column(col)

        if self._notebook:
            self._save_column_order()
            self._notebook.get_listeners("table_changed").notify(
                self._notebook, self._current_table)

    def _on_column_width_change(self, col, pspec):
        width = col.get_width()
        if (self._notebook and
                self._col_widths.get(col.attr, None) != width):
            self._col_widths[col.attr] = width
            self._save_column_widths()
            self._notebook.get_listeners("table_changed").notify(
                self._notebook, self._current_table)

    # ====================================================
    # Actions

    def view_nodes(self, nodes, nested=True):
        print(f"List view_nodes called with nodes: {[node.get_title() for node in nodes]}")
        if len(nodes) > 1:
            nested = False

        self._sel_nodes = nodes
        self.rich_model.set_nested(nested)

        self.set_master_node(None)
        self.rich_model.set_root_nodes(nodes)

        if len(nodes) == 1:
            self.load_sorting(nodes[0], self.model)

        for node in nodes:
            # Convert tuple to Gtk.TreePath
            path_tuple = treemodel.get_path_from_node(
                self.model, node, self.rich_model.get_node_column_pos())
            path = Gtk.TreePath.new_from_indices(path_tuple)
            self.expand_to_path(path)

        self.set_sensitive(len(nodes) > 0)
        self.display_page_count()

        self.emit("select-nodes", [])

    def get_root_nodes(self):
        return self.rich_model.get_root_nodes() if self.rich_model else []

    def append_node(self, node):
        if self.get_master_node() is not None:
            return

        self.rich_model.append(node)

        if node.get_attr("expanded2", False):
            self.expand_to_path(treemodel.get_path_from_node(
                self.model, node, self.rich_model.get_node_column_pos()))

        self.set_sensitive(True)

    def display_page_count(self, npages=None):
        if npages is None:
            npages = self.count_pages(self.get_root_nodes())

        if npages != 1:
            self.set_status(_("%d pages") % npages, "stats")
        else:
            self.set_status(_("1 page"), "stats")

    def count_pages(self, roots):
        def walk(node):
            npages = 1
            if (self.rich_model.get_nested() and
                    node.get_attr("expanded2", False)):
                for child in node.get_children():
                    npages += walk(child)
            return npages

        return sum(walk(child) for node in roots
                   for child in node.get_children())

    def edit_node(self, page):
        path = treemodel.get_path_from_node(
            self.model, page, self.rich_model.get_node_column_pos())
        if path is None:
            self.emit("goto-node", page)
            path = treemodel.get_path_from_node(
                self.model, page, self.rich_model.get_node_column_pos())
            assert path is not None
        self.set_cursor_on_cell(path, self.title_column, self.title_text, True)
        path, col = self.get_cursor()
        self.scroll_to_cell(path, col, False, 0.0, 0.0)  # Updated for GTK 4

    def save_sorting(self, node):
        info_sort, sort_dir = self.model.get_sort_column_id()
        sort_dir = 1 if sort_dir == Gtk.SortType.ASCENDING else 0

        col = (self.rich_model.get_column_by_name("order")
               if info_sort is None or info_sort < 0
               else self.rich_model.get_column(info_sort))

        if col.attr:
            node.set_attr("info_sort", col.attr)
            node.set_attr("info_sort_dir", sort_dir)

    def load_sorting(self, node, model):
        info_sort = node.get_attr("info_sort", "order")
        sort_dir = node.get_attr("info_sort_dir", 1)
        sort_dir = Gtk.SortType.ASCENDING if sort_dir else Gtk.SortType.DESCENDING

        if info_sort == "":
            info_sort = "order"

        for col in self.rich_model.get_columns():
            if info_sort == col.attr and col.name.endswith("_sort"):
                model.set_sort_column_id(col.pos, sort_dir)

        self._update_reorder()

    def set_status(self, text, bar="status"):
        if self.on_status:
            self.on_status(text, bar=bar)

    def _on_node_changed_end(self, model, nodes):
        super()._on_node_changed_end(model, nodes)

        if self.rich_model.get_nested():
            child = model.iter_children(None)
            while child is not None:
                self.expand_row(model.get_path(child), False)
                child = model.iter_next(child)

    def _on_listview_row_expanded(self, treeview, it, path):
        self.display_page_count()

    def _on_listview_row_collapsed(self, treeview, it, path):
        self.display_page_count()