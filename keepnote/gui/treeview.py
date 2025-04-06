# PyGObject imports
from gi import require_version
require_version('Gtk', '4.0')  # GTK4 change
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf  # GTK4 change

# KeepNote imports
from keepnote.gui import treemodel
from keepnote.gui import basetreeview
from keepnote.gui.icons import get_node_icon

class KeepNoteTreeView(basetreeview.KeepNoteBaseTreeView):
    """
    TreeView widget for the KeepNote NoteBook
    """

    def __init__(self):
        super().__init__()

        self._notebook = None

        # 使用自定义模型
        self.model = treemodel.KeepNoteTreeModel()
        self.set_model(self.model)

        # Treeview signals
        # GTK3 写法（不可用于 GTK4）
        # self.connect("key-release-event", self.on_key_released)

        # GTK4 推荐写法：
        controller = Gtk.EventControllerKey()
        controller.connect("key-released", self.on_key_released)
        self.add_controller(controller)

        # Selection config
        self.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        # Tree style
        self.set_headers_visible(False)
        self.set_property("enable-tree-lines", True)  # GTK4: 保留无效，仅用于向后兼容

        self._setup_columns()
        self.set_sensitive(False)

    def _setup_columns(self):
        self.clear_columns()

        if self._notebook is None:
            return

        # 创建树视图列
        self.column = Gtk.TreeViewColumn()
        self.column.set_clickable(False)
        self.append_column(self.column)

        # 添加图标和标题渲染器
        renderer_pixbuf = Gtk.CellRendererPixbuf()
        renderer_text = Gtk.CellRendererText()
        self.column.pack_start(renderer_pixbuf, False)
        self.column.pack_start(renderer_text, True)

        # 确保模型包含足够的列
        self._add_model_column("icon")      # 图标列
        self._add_model_column("icon_open") # 展开时的图标列
        self._add_model_column("title")     # 标题列
        self._add_model_column("fgcolor")   # 前景色
        self._add_model_column("bgcolor")   # 背景色

        self.column.add_attribute(renderer_pixbuf, "pixbuf", self.model.get_column_by_name("icon").pos)
        # GTK4 不再支持 pixbuf-expander-open，保留注释如下：
        # self.column.add_attribute(renderer_pixbuf, "pixbuf-expander-open", self.model.get_column_by_name("icon_open").pos)
        self.column.add_attribute(renderer_text, "text", self.model.get_column_by_name("title").pos)
        self.column.add_attribute(renderer_text, "foreground", self.model.get_column_by_name("fgcolor").pos)
        self.column.add_attribute(renderer_text, "cell-background", self.model.get_column_by_name("bgcolor").pos)

        # 使树视图可搜索
        self.set_search_column(self.model.get_column_by_name("title").pos)

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
            return self.popup_menu(event.x, event.y, event.button, event.time)

        if event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
            nodes = self.get_selected_nodes()
            if nodes:
                self.emit("activate-node", nodes[0])

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
                path = Gtk.TreePath.new_from_indices([0])
                self.expand_to_path(path)

    def edit_node(self, node):
        path = treemodel.get_path_from_node(
            self.model, node,
            self.rich_model.get_node_column_pos())
        GLib.idle_add(lambda: self.set_cursor_on_cell(
            path, self.column, self.title_text, True))
