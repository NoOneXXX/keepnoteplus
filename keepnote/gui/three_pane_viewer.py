# KeepNote
# Copyright (c) 2008-2011 Matt Rasmussen
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
from gi.repository import Gtk, Gdk, GObject

# KeepNote imports
import keepnote
from keepnote.notebook import NoteBookError
from keepnote.gui import add_actions, Action, CONTEXT_MENU_ACCEL_PATH, DEFAULT_COLORS
from keepnote import notebook as notebooklib
from keepnote.gui import richtext
from keepnote.gui.richtext import RichTextError
from keepnote.gui.treeview import KeepNoteTreeView
from keepnote.gui.listview import KeepNoteListView
from keepnote.gui.editor_richtext import RichTextEditor
from keepnote.gui.editor_text import TextEditor
from keepnote.gui.editor_multi import ContentEditor
from keepnote.gui.icon_menu import IconMenu
from keepnote.gui.viewer import Viewer
from keepnote.gui.icons import lookup_icon_filename
from keepnote.gui.colortool import ColorMenu

_ = keepnote.translate

DEFAULT_VSASH_POS = 200
DEFAULT_HSASH_POS = 200
DEFAULT_VIEW_MODE = "vertical"


class ThreePaneViewer(Viewer):
    """A viewer with a treeview, listview, and editor"""

    def __init__(self, app, main_window, viewerid=None):
        super().__init__(app, main_window, viewerid, viewer_name="three_pane_viewer")
        self._ui_ready = False

        # Node selections
        self._current_page = None
        self._treeview_sel_nodes = []
        self._queue_list_select = []
        self._new_page_occurred = False
        self.back_button = None
        self._view_mode = DEFAULT_VIEW_MODE

        self.connect("history-changed", self._on_history_changed)

        # Widgets
        # Treeview
        self.treeview = KeepNoteTreeView()
        self.treeview.set_get_node(self._app.get_node)
        self.treeview.connect("select-nodes", self._on_tree_select)
        self.treeview.connect("delete-node", self.on_delete_node)
        self.treeview.connect("error", lambda w, t, e: self.emit("error", t, e))
        self.treeview.connect("edit-node", self._on_edit_node)
        self.treeview.connect("goto-node", self.on_goto_node)
        self.treeview.connect("activate-node", self.on_activate_node)
        self.treeview.connect("drop-file", self._on_attach_file)

        # Listview
        self.listview = KeepNoteListView()
        self.listview.set_get_node(self._app.get_node)
        self.listview.connect("select-nodes", self._on_list_select)
        self.listview.connect("delete-node", self.on_delete_node)
        self.listview.connect("goto-node", self.on_goto_node)
        self.listview.connect("activate-node", self.on_activate_node)
        self.listview.connect("goto-parent-node", lambda w: self.on_goto_parent_node())
        self.listview.connect("error", lambda w, t, e: self.emit("error", t, e))
        self.listview.connect("edit-node", self._on_edit_node)
        self.listview.connect("drop-file", self._on_attach_file)
        self.listview.on_status = self.set_status

        # Editor
        self.editor = ContentEditor(self._app)
        rich_editor = RichTextEditor(self._app)
        self.editor.add_editor("text/xhtml+xml", rich_editor)
        self.editor.add_editor("text", TextEditor(self._app))
        self.editor.set_default_editor(rich_editor)

        self.editor.connect("view-node", self._on_editor_view_node)
        self.editor.connect("child-activated", self._on_child_activated)
        self.editor.connect("visit-node", lambda w, n: self.goto_node(n, False))
        self.editor.connect("error", lambda w, t, e: self.emit("error", t, e))
        self.editor.connect("window-request", lambda w, t: self.emit("window-request", t))
        self.editor.view_nodes([])

        self.editor_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.editor_pane.pack_start(self.editor, True, True, 0)

        # Layout
        self._hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(self._hpaned, True, True, 0)
        self._hpaned.set_position(DEFAULT_HSASH_POS)

        self._paned2 = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self._hpaned.pack2(self._paned2, resize=True, shrink=False)
        self._paned2.set_position(DEFAULT_VSASH_POS)

        # Treeview with scrollbars
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.treeview)
        self._hpaned.pack1(sw, resize=False, shrink=True)

        # Listview with scrollbars
        self._listview_sw = Gtk.ScrolledWindow()
        self._listview_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._listview_sw.set_shadow_type(Gtk.ShadowType.IN)
        self._listview_sw.add(self.listview)
        self._paned2.pack1(self._listview_sw, resize=True, shrink=True)

        # Editor
        self._paned2.pack2(self.editor_pane, resize=True, shrink=False)

        self.treeview.grab_focus()

    def set_notebook(self, notebook):
        self._app.ref_notebook(notebook)
        if self._notebook is not None:
            self._app.unref_notebook(self._notebook)

        if self._notebook:
            self._notebook.node_changed.remove(self.on_notebook_node_changed)

        if notebook:
            notebook.node_changed.add(self.on_notebook_node_changed)

        self._notebook = notebook
        self.editor.set_notebook(notebook)
        self.listview.set_notebook(notebook)
        self.treeview.set_notebook(notebook)

        if self.treeview.get_popup_menu():
            self.treeview.get_popup_menu().iconmenu.set_notebook(notebook)
            self.listview.get_popup_menu().iconmenu.set_notebook(notebook)
            colors = self._notebook.pref.get("colors", default=DEFAULT_COLORS) if self._notebook else DEFAULT_COLORS
            self.treeview.get_popup_menu().fgcolor_menu.set_colors(colors)
            self.treeview.get_popup_menu().bgcolor_menu.set_colors(colors)
            self.listview.get_popup_menu().fgcolor_menu.set_colors(colors)
            self.listview.get_popup_menu().bgcolor_menu.set_colors(colors)

        self._load_selections()
        self.treeview.grab_focus()

    def load_preferences(self, app_pref, first_open=False):
        p = app_pref.get("viewers", "three_pane_viewer", define=True)
        vsash_pos = p.get("vsash_pos", DEFAULT_VSASH_POS)
        hsash_pos = p.get("hsash_pos", DEFAULT_HSASH_POS)
        print(f"vsash_pos: {vsash_pos} (type: {type(vsash_pos)})")
        print(f"hsash_pos: {hsash_pos} (type: {type(hsash_pos)})")
        self.set_view_mode(p.get("view_mode", DEFAULT_VIEW_MODE))
        self._paned2.set_property("position-set", True)
        self._hpaned.set_property("position-set", True)
        self._paned2.set_position(int(vsash_pos))
        self._hpaned.set_position(int(hsash_pos))

        self.listview.load_preferences(app_pref, first_open)
        try:
            self.treeview.set_property("enable-tree-lines", app_pref.get("look_and_feel", "treeview_lines", default=True))
        except:
            pass

        self.editor.load_preferences(app_pref, first_open)
        if self._ui_ready:
            self.remove_ui(self._main_window)
            self.add_ui(self._main_window)

    def save_preferences(self, app_pref):
        p = app_pref.get("viewers", "three_pane_viewer")
        p["view_mode"] = self._view_mode
        p["vsash_pos"] = self._paned2.get_position()
        p["hsash_pos"] = self._hpaned.get_position()

        self.listview.save_preferences(app_pref)
        self.editor.save_preferences(app_pref)

    def save(self):
        self.listview.save()
        self.editor.save()
        self._save_selections()

    def on_notebook_node_changed(self, nodes):
        self.emit("modified", True)

    def undo(self):
        self.editor.undo()

    def redo(self):
        self.editor.redo()

    def get_editor(self):
        return self.editor.get_editor()

    def set_status(self, text, bar="status"):
        self.emit("status", text, bar)

    def set_view_mode(self, mode):
        vsash = self._paned2.get_position()
        self._paned2.remove(self._listview_sw)
        self._paned2.remove(self.editor_pane)
        self._hpaned.remove(self._paned2)

        if mode == "vertical":
            self._paned2 = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        else:
            self._paned2 = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        self._paned2.set_position(vsash)
        self._paned2.show()
        self._hpaned.pack2(self._paned2, resize=True, shrink=False)
        self._hpaned.show()

        self._paned2.pack1(self._listview_sw, resize=True, shrink=True)
        self._paned2.pack2(self.editor_pane, resize=True, shrink=False)
        self._view_mode = mode

    def _load_selections(self):
        if self._notebook:
            info = self._notebook.pref.get("viewers", "ids", self._viewerid, define=True)
            nodes = [node for node in (self._notebook.get_node_by_id(i) for i in info.get("selected_treeview_nodes", [])) if node is not None]
            self.treeview.select_nodes(nodes)
            nodes = [node for node in (self._notebook.get_node_by_id(i) for i in info.get("selected_listview_nodes", [])) if node is not None]
            self.listview.select_nodes(nodes)

    def _save_selections(self):
        if self._notebook is not None:
            info = self._notebook.pref.get("viewers", "ids", self._viewerid, define=True)
            info["selected_treeview_nodes"] = [node.get_attr("nodeid") for node in self.treeview.get_selected_nodes()]
            info["selected_listview_nodes"] = [node.get_attr("nodeid") for node in self.listview.get_selected_nodes()]
            self._notebook.set_preferences_dirty()

    def get_current_node(self):
        return self._current_page

    def get_selected_nodes(self):
        if self.treeview.is_focus():
            return self.treeview.get_selected_nodes()
        nodes = self.listview.get_selected_nodes()
        return nodes if nodes else self.treeview.get_selected_nodes()

    def _on_history_changed(self, viewer, history):
        if self._ui_ready and self.back_button:
            self.back_button.set_sensitive(history.has_back())
            self.forward_button.set_sensitive(history.has_forward())

    def get_focused_widget(self, default=None):
        if self.treeview.is_focus():
            return self.treeview
        if self.listview.is_focus():
            return self.listview
        return default

    def on_delete_node(self, widget, nodes=None):
        if nodes is None:
            nodes = self.get_selected_nodes()
        if not nodes:
            return

        if self._main_window.confirm_delete_nodes(nodes):
            if len(nodes) == 1:
                node = nodes[0]
                widget = self.get_focused_widget(self.listview)
                parent = node.get_parent()
                children = parent.get_children()
                i = children.index(node)
                widget.select_nodes([children[i+1]] if i < len(children) - 1 else [parent])
            else:
                widget = self.get_focused_widget(self.listview)
                widget.select_nodes([])

            try:
                for node in nodes:
                    node.trash()
            except NoteBookError as e:
                self.emit("error", e.msg, e)

    def _on_editor_view_node(self, editor, node):
        self._history.add(node.get_attr("nodeid"))
        self.emit("history-changed", self._history)

    def _on_child_activated(self, editor, textview, child):
        if self._current_page and isinstance(child, richtext.RichTextImage):
            filename = self._current_page.get_file(child.get_filename())
            self._app.run_external_app("image_viewer", filename)

    def _on_tree_select(self, treeview, nodes):
        if self._treeview_sel_nodes == nodes:
            return
        self._treeview_sel_nodes = nodes
        self.listview.view_nodes(nodes)
        if self._queue_list_select:
            self.listview.select_nodes(self._queue_list_select)
            self._queue_list_select = []
        self.listview.select_nodes(nodes)

    def _on_list_select(self, listview, nodes):
        self._current_page = nodes[0] if len(nodes) == 1 else None
        try:
            self.editor.view_nodes(nodes)
        except RichTextError as e:
            self.emit("error", f"Could not load page '{nodes[0].get_title()}'.", e)
        self.emit("current-node", self._current_page)

    def on_goto_node(self, widget, node):
        self.goto_node(node, direct=False)

    def on_activate_node(self, widget, node):
        if self.viewing_search():
            self.goto_node(node, direct=False)
        elif node and node.has_attr("payload_filename"):
            self._main_window.on_view_node_external_app("file_launcher", node, kind="file")
        else:
            self.goto_node(node, direct=True)

    def on_goto_parent_node(self, node=None):
        if node is None:
            nodes = self.get_selected_nodes()
            if not nodes:
                return
            node = nodes[0]
        parent = node.get_parent()
        if parent:
            self.goto_node(parent, direct=False)

    def _on_edit_node(self, widget, node, attr, value):
        if self._new_page_occurred:
            self._new_page_occurred = False
            if node.get_attr("content_type") != notebooklib.CONTENT_TYPE_DIR:
                self.goto_editor()

    def _on_attach_file(self, widget, parent, index, uri):
        self._app.attach_file(uri, parent, index)

    def _on_attach_file_menu(self):
        nodes = self.get_selected_nodes()
        if nodes:
            self._app.on_attach_file(nodes[0], self.get_toplevel())

    def new_node(self, kind, pos, parent=None):
        if self._notebook is None:
            return
        self.treeview.cancel_editing()
        self.listview.cancel_editing()
        if parent is None:
            nodes = self.get_selected_nodes()
            parent = nodes[0] if len(nodes) == 1 else self._notebook
        node = Viewer.new_node(self, kind, pos, parent)
        self._view_new_node(node)

    def on_new_dir(self):
        self.new_node(notebooklib.CONTENT_TYPE_DIR, "sibling")

    def on_new_page(self):
        self.new_node(notebooklib.CONTENT_TYPE_PAGE, "sibling")

    def on_new_child_page(self):
        self.new_node(notebooklib.CONTENT_TYPE_PAGE, "child")

    def _view_new_node(self, node):
        self._new_page_occurred = True
        self.goto_node(node)
        if node in self.treeview.get_selected_nodes():
            self.treeview.edit_node(node)
        else:
            self.listview.edit_node(node)

    def _on_rename_node(self):
        nodes = self.get_selected_nodes()
        if nodes:
            widget = self.get_focused_widget(self.listview)
            widget.edit_node(nodes[0])

    def goto_node(self, node, direct=False):
        if node is None:
            nodes = self.listview.get_selected_nodes()
            if not nodes:
                return
            node = nodes[0]

        if direct:
            self.treeview.select_nodes([node])
        else:
            treenodes = self.treeview.get_selected_nodes()
            path = []
            ptr = node
            while ptr:
                if ptr in treenodes:
                    path = []
                    break
                path.append(ptr)
                ptr = ptr.get_parent()

            node2 = None
            for n in reversed(path):
                if not self.treeview.is_node_expanded(n):
                    node2 = n
                    break

            if node2:
                self.treeview.select_nodes([node2])
            if node2 != node:
                self.listview.select_nodes([node])

    def goto_next_node(self):
        widget = self.get_focused_widget(self.treeview)
        path, col = widget.get_cursor()
        if path:
            path2 = path[:-1] + (path[-1] + 1,)
            nchildren = widget.get_model().iter_n_children(widget.get_model().get_iter(path[:-1]) if len(path) > 1 else None)
            if path2[-1] < nchildren:
                widget.set_cursor(path2)

    def goto_prev_node(self):
        widget = self.get_focused_widget(self.treeview)
        path, col = widget.get_cursor()
        if path and path[-1] > 0:
            path2 = path[:-1] + (path[-1] - 1,)
            widget.set_cursor(path2)

    def expand_node(self, all=False):
        widget = self.get_focused_widget(self.treeview)
        path, col = widget.get_cursor()
        if path:
            widget.expand_row(path, all)

    def collapse_node(self, all=False):
        widget = self.get_focused_widget(self.treeview)
        path, col = widget.get_cursor()
        if path:
            if all:
                widget.collapse_all_beneath(path)
            else:
                widget.collapse_row(path)

    def on_copy_tree(self):
        widget = self._main_window.get_focus()
        if GObject.signal_lookup("copy-tree-clipboard", widget):
            widget.emit("copy-tree-clipboard")

    def start_search_result(self):
        self.treeview.select_nodes([])
        self.listview.view_nodes([], nested=False)

    def add_search_result(self, node):
        self.listview.append_node(node)

    def end_search_result(self):
        try:
            self.listview.get_selection().select_path((0,))
        except:
            pass

    def viewing_search(self):
        return len(self.treeview.get_selected_nodes()) == 0 and len(self.listview.get_selected_nodes()) > 0

    def goto_treeview(self):
        self.treeview.grab_focus()

    def goto_listview(self):
        self.listview.grab_focus()

    def goto_editor(self):
        self.editor.grab_focus()

    def add_ui(self, window):
        assert window == self._main_window
        self._ui_ready = True
        self._action_group = Gtk.ActionGroup(name="Viewer")
        self._uis = []
        add_actions(self._action_group, self._get_actions())
        self._main_window.get_uimanager().insert_action_group(self._action_group, 0)

        for s in self._get_ui():
            self._uis.append(self._main_window.get_uimanager().add_ui_from_string(s))

        uimanager = self._main_window.get_uimanager()
        uimanager.ensure_update()

        self.back_button = uimanager.get_widget("/main_tool_bar/Viewer/Back")
        self.forward_button = uimanager.get_widget("/main_tool_bar/Viewer/Forward")
        self.editor.add_ui(window)

        menu1 = uimanager.get_widget("/popup_menus/treeview_popup").get_submenu()
        self.treeview.set_popup_menu(menu1)
        menu1.set_accel_path(CONTEXT_MENU_ACCEL_PATH)
        menu1.set_accel_group(uimanager.get_accel_group())

        menu1.iconmenu = self._setup_icon_menu()
        item = uimanager.get_widget("/popup_menus/treeview_popup/Change Note Icon")
        item.set_submenu(menu1.iconmenu)
        item.show()

        menu1.fgcolor_menu = self._setup_color_menu("fg")
        item = uimanager.get_widget("/popup_menus/treeview_popup/Change Fg Color")
        item.set_submenu(menu1.fgcolor_menu)
        item.show()

        menu1.bgcolor_menu = self._setup_color_menu("bg")
        item = uimanager.get_widget("/popup_menus/treeview_popup/Change Bg Color")
        item.set_submenu(menu1.bgcolor_menu)
        item.show()

        menu2 = uimanager.get_widget("/popup_menus/listview_popup").get_submenu()
        self.listview.set_popup_menu(menu2)
        menu2.set_accel_group(uimanager.get_accel_group())
        menu2.set_accel_path(CONTEXT_MENU_ACCEL_PATH)

        menu2.iconmenu = self._setup_icon_menu()
        item = uimanager.get_widget("/popup_menus/listview_popup/Change Note Icon")
        item.set_submenu(menu2.iconmenu)
        item.show()

        menu2.fgcolor_menu = self._setup_color_menu("fg")
        item = uimanager.get_widget("/popup_menus/listview_popup/Change Fg Color")
        item.set_submenu(menu2.fgcolor_menu)
        item.show()

        menu2.bgcolor_menu = self._setup_color_menu("bg")
        item = uimanager.get_widget("/popup_menus/listview_popup/Change Bg Color")
        item.set_submenu(menu2.bgcolor_menu)
        item.show()

    def _setup_icon_menu(self):
        iconmenu = IconMenu()
        iconmenu.connect("set-icon", lambda w, i: self._app.on_set_icon(i, "", self.get_selected_nodes()))
        iconmenu.new_icon.connect("activate", lambda w: self._app.on_new_icon(self.get_selected_nodes(), self._notebook, self._main_window))
        iconmenu.set_notebook(self._notebook)
        return iconmenu

    def _setup_color_menu(self, kind):
        def on_set_color(w, color):
            for node in self.get_selected_nodes():
                attr = "title_fgcolor" if kind == "fg" else "title_bgcolor"
                if color:
                    node.set_attr(attr, color)
                else:
                    node.del_attr(attr)

        def on_set_colors(w, colors):
            if self._notebook:
                self._notebook.pref.set("colors", list(colors))
                self._app.get_listeners("colors_changed").notify(self._notebook, colors)

        def on_new_colors(notebook, colors):
            if self._notebook == notebook:
                menu.set_colors(colors)

        colors = self._notebook.pref.get("colors", default=DEFAULT_COLORS) if self._notebook else DEFAULT_COLORS
        menu = ColorMenu(colors)
        menu.connect("set-color", on_set_color)
        menu.connect("set-colors", on_set_colors)
        self._app.get_listeners("colors_changed").add(on_new_colors)
        return menu

    def remove_ui(self, window):
        assert self._main_window == window
        self._ui_ready = False
        self.editor.remove_ui(self._main_window)
        for ui in reversed(self._uis):
            self._main_window.get_uimanager().remove_ui(ui)
        self._uis = []
        self._main_window.get_uimanager().ensure_update()
        self._main_window.get_uimanager().remove_action_group(self._action_group)
        self._action_group = None

    def _get_ui(self):
        return ["""
        <ui>
        <menubar name="main_menu_bar">
          <menu action="File">
            <placeholder name="Viewer">
              <menuitem action="New Page"/>
              <menuitem action="New Child Page"/>
              <menuitem action="New Folder"/>
            </placeholder>
          </menu>
          <menu action="Edit">
            <placeholder name="Viewer">
              <menuitem action="Attach File"/>
              <separator/>
              <placeholder name="Editor"/>
            </placeholder>
          </menu>
          <placeholder name="Viewer">
            <placeholder name="Editor"/>
            <menu action="View">
              <menuitem action="View Note in File Explorer"/>
              <menuitem action="View Note in Text Editor"/>
              <menuitem action="View Note in Web Browser"/>
              <menuitem action="Open File"/>
            </menu>
          </placeholder>
          <menu action="Go">
            <placeholder name="Viewer">
              <menuitem action="Back"/>
              <menuitem action="Forward"/>
              <separator/>
              <menuitem action="Go to Note"/>
              <menuitem action="Go to Parent Note"/>
              <menuitem action="Go to Next Note"/>
              <menuitem action="Go to Previous Note"/>
              <menuitem action="Expand Note"/>
              <menuitem action="Collapse Note"/>
              <menuitem action="Expand All Child Notes"/>
              <menuitem action="Collapse All Child Notes"/>
              <separator/>
              <menuitem action="Go to Tree View"/>
              <menuitem action="Go to List View"/>
              <menuitem action="Go to Editor"/>
              <placeholder name="Editor"/>
            </placeholder>
          </menu>
          <menu action="Tools">
          </menu>
        </menubar>
        <toolbar name="main_tool_bar">
          <placeholder name="Viewer">
            <toolitem action="New Folder"/>
            <toolitem action="New Page"/>
            <separator/>
            <toolitem action="Back"/>
            <toolitem action="Forward"/>
            <separator/>
            <placeholder name="Editor"/>
          </placeholder>
        </toolbar>
        <menubar name="popup_menus">
          <menu action="treeview_popup">
            <menuitem action="New Page"/>
            <menuitem action="New Child Page"/>
            <menuitem action="New Folder"/>
            <menuitem action="Attach File"/>
            <placeholder name="New"/>
            <separator/>
            <menuitem action="Cut"/>
            <menuitem action="Copy"/>
            <menuitem action="Copy Tree"/>
            <menuitem action="Paste"/>
            <separator/>
            <menuitem action="Delete Note"/>
            <menuitem action="Rename Note"/>
            <menuitem action="Change Note Icon"/>
            <menuitem action="Change Fg Color"/>
            <menuitem action="Change Bg Color"/>
            <menu action="View Note As">
              <menuitem action="View Note in File Explorer"/>
              <menuitem action="View Note in Text Editor"/>
              <menuitem action="View Note in Web Browser"/>
              <menuitem action="Open File"/>
            </menu>
          </menu>
          <menu action="listview_popup">
            <menuitem action="Go to Note"/>
            <menuitem action="Go to Parent Note"/>
            <separator/>
            <menuitem action="New Page"/>
            <menuitem action="New Child Page"/>
            <menuitem action="New Folder"/>
            <menuitem action="Attach File"/>
            <placeholder name="New"/>
            <separator/>
            <menuitem action="Cut"/>
            <menuitem action="Copy"/>
            <menuitem action="Copy Tree"/>
            <menuitem action="Paste"/>
            <separator/>
            <menuitem action="Delete Note"/>
            <menuitem action="Rename Note"/>
            <menuitem action="Change Note Icon"/>
            <menuitem action="Change Fg Color"/>
            <menuitem action="Change Bg Color"/>
            <menu action="View Note As">
              <menuitem action="View Note in File Explorer"/>
              <menuitem action="View Note in Text Editor"/>
              <menuitem action="View Note in Web Browser"/>
              <menuitem action="Open File"/>
            </menu>
          </menu>
        </menubar>
        </ui>
        """]

    def _get_actions(self):
        return [Action(*x) for x in [
            ("treeview_popup", None, "", "", None, lambda w: None),
            ("listview_popup", None, "", "", None, lambda w: None),
            ("Copy Tree", "gtk-copy", _("Copy _Tree"), "<control><shift>C", _("Copy entire tree"), lambda w: self.on_copy_tree()),
            ("New Page", "gtk-new", _("New _Page"), "<control>N", _("Create a new page"), lambda w: self.on_new_page(), "note-new.png"),
            ("New Child Page", "gtk-new", _("New _Child Page"), "<control><shift>N", _("Create a new child page"), lambda w: self.on_new_child_page(), "note-new.png"),
            ("New Folder", "gtk-directory", _("New _Folder"), "<control><shift>M", _("Create a new folder"), lambda w: self.on_new_dir(), "folder-new.png"),
            ("Attach File", "gtk-add", _("_Attach File..."), "", _("Attach a file to the notebook"), lambda w: self._on_attach_file_menu()),
            ("Back", "gtk-go-back", _("_Back"), "", None, lambda w: self.visit_history(-1)),
            ("Forward", "gtk-go-forward", _("_Forward"), "", None, lambda w: self.visit_history(1)),
            ("Go to Note", "gtk-jump-to", _("Go to _Note"), "", None, lambda w: self.on_goto_node(None, None)),
            ("Go to Parent Note", "gtk-go-back", _("Go to _Parent Note"), "<shift><alt>Left", None, lambda w: self.on_goto_parent_node()),
            ("Go to Next Note", "gtk-go-down", _("Go to Next N_ote"), "<alt>Down", None, lambda w: self.goto_next_node()),
            ("Go to Previous Note", "gtk-go-up", _("Go to _Previous Note"), "<alt>Up", None, lambda w: self.goto_prev_node()),
            ("Expand Note", "gtk-add", _("E_xpand Note"), "<alt>Right", None, lambda w: self.expand_node()),
            ("Collapse Note", "gtk-remove", _("_Collapse Note"), "<alt>Left", None, lambda w: self.collapse_node()),
            ("Expand All Child Notes", "gtk-add", _("Expand _All Child Notes"), "<shift><alt>Right", None, lambda w: self.expand_node(True)),
            ("Collapse All Child Notes", "gtk-remove", _("Collapse A_ll Child Notes"), "<shift><alt>Left", None, lambda w: self.collapse_node(True)),
            ("Go to Tree View", None, _("Go to _Tree View"), "<control>T", None, lambda w: self.goto_treeview()),
            ("Go to List View", None, _("Go to _List View"), "<control>Y", None, lambda w: self.goto_listview()),
            ("Go to Editor", None, _("Go to _Editor"), "<control>D", None, lambda w: self.goto_editor()),
            ("Delete Note", "gtk-delete", _("_Delete"), "", None, self.on_delete_node),
            ("Rename Note", "gtk-edit", _("_Rename"), "", None, lambda w: self._on_rename_node()),
            ("Change Note Icon", None, _("_Change Note Icon"), "", None, lambda w: None, lookup_icon_filename(None, "folder-red.png")),
            ("Change Fg Color", None, _("Change _Fg Color")),
            ("Change Bg Color", None, _("Change _Bg Color")),
        ]]