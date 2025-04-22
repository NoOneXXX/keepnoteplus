# PyGObject imports
from gi import require_version

require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, GObject

# KeepNote imports
import keepnote
from keepnote.gui import add_actions, Action
from keepnote.gui.three_pane_viewer import ThreePaneViewer
from keepnote.gui.viewer import Viewer
from keepnote.gui.icons import get_node_icon

_ = keepnote.translate


class TwoWayDict(object):
    def __init__(self):
        self._lookup1 = {}
        self._lookup2 = {}

    def add(self, item1, item2):
        self._lookup1[item1] = item2
        self._lookup2[item2] = item1

    def get1(self, item1, default=None):
        return self._lookup1.get(item1, default)

    def get2(self, item2, default=None):
        return self._lookup2.get(item2, default)


class TabbedViewer(Viewer):
    """A viewer with a treeview, listview, and editor"""

    def __init__(self, app, main_window, viewerid=None, default_viewer=ThreePaneViewer):
        super().__init__(app, main_window, viewerid, viewer_name="tabbed_viewer")
        self._app = app  # Ensure _app is passed correctly
        if self._app is None:
            print("ERROR: _app is not initialized.")
            return  # Prevent further initialization if _app is None
        self._default_viewer = default_viewer
        self._current_viewer = None
        self._callbacks = {}
        self._ui_ready = False
        self._null_viewer = Viewer(app, main_window)
        self._tab_names = {}

        # Viewer registry
        self._viewer_lookup = TwoWayDict()
        # self._viewer_lookup.add(ThreePaneViewer(app, main_window).get_name(), ThreePaneViewer)
        self._viewer_lookup.add("three_pane_viewer", ThreePaneViewer)
        self._viewer_pages = {}  # key: widget, value: viewer

        # Layout
        self._tabs = Gtk.Notebook()
        self._tabs.set_show_border(False)
        self._tabs.set_scrollable(True)
        self._tabs.connect("switch-page", self._on_switch_tab)
        self._tabs.connect("page-added", self._on_tab_added)
        self._tabs.connect("page-removed", self._on_tab_removed)

        # Replace "button-press-event" with Gtk.GestureClick
        click_controller = Gtk.GestureClick.new()
        click_controller.set_button(1)  # Left-click
        click_controller.connect("pressed", self._on_button_press)
        self._tabs.add_controller(click_controller)

        # self.append(self._tabs)  # Changed from pack_start to append
        if self._tabs.get_parent():
            print("⚠️ self._tabs already has a parent, unparenting it")
            self._tabs.unparent()
        print("➕ Appending self._tabs to TabbedViewer")
        self.append(self._tabs)

        # Initialize with a single tab
        self.new_tab()

    def get_current_viewer(self):
        """Get currently focused viewer"""
        pos = self._tabs.get_current_page()
        if pos == -1:
            return self._null_viewer
        return self._tabs.get_nth_page(pos)

    def iter_viewers(self):
        """Iterate through all viewers"""
        for i in range(self._tabs.get_n_pages()):
            yield self._tabs.get_nth_page(i)

    def new_tab(self, viewer=None, init="current_node"):
        """Open a new tab with a viewer"""
        self._current_viewer = viewer
        if viewer is None:
            viewer = self._default_viewer(self._app, self._main_window)
            self._current_viewer = viewer  # 修复 viewer 的引用丢失
        widget = viewer.get_widget()
        if widget.get_parent():
            print("⚠️ new_tab(): viewer widget already has parent, unparenting")
            widget.unparent()

        import uuid
        label_text = "Notebook %s" % str(uuid.uuid4())[:8]
        print("🧪 [DEBUG] Generated label:", label_text)
        label = Gtk.Label(label=label_text)
        # label = TabLabel(self, viewer, None, label_text)  # 暂时禁用
        # label = Gtk.Label(label=label_text)  # ✅ 用纯 label 测试结构是否稳定
        # label.connect("new-name", lambda w, text: self._on_new_tab_name(viewer, text))
        if hasattr(label, "connect") and "new-name" in GObject.signal_list_names(type(label)):
            label.connect("new-name", lambda w, text: self._on_new_tab_name(viewer, text))

        self._current_viewer = viewer  # ✅ 保存 viewer 引用

        widget = viewer.get_widget()
        if widget is None:
            print("❌ ERROR: viewer.get_widget() is None!")
            return
        if widget.get_parent():
            print("⚠️ new_tab(): viewer widget already has parent, unparenting")
            widget.unparent()

        if not hasattr(viewer, "get_widget"):
            print("❌ Error: viewer is not a Viewer instance")
            return

        self._tabs.append_page(widget, label)
        self._tabs.set_tab_reorderable(widget, True)  # ✅ 改为操作 widget 而不是 viewer
        self._tab_names[viewer] = None
        # self._tabs.append_page(widget, label)
        # self._tabs.set_tab_reorderable(widget, True)
        # self._tab_names[viewer] = None
        self._viewer_pages[widget] = viewer  # ✅ 记录真实 viewer
        # Setup viewer signals
        self._callbacks[viewer] = [
            viewer.connect("error", lambda w, m, e: self.emit("error", m, e)),
            viewer.connect("status", lambda w, m, b: self.emit("status", m, b)),
            viewer.connect("window-request", lambda w, t: self.emit("window-request", t)),
            viewer.connect("current-node", self.on_tab_current_node),
            viewer.connect("modified", self.on_tab_modified)
        ]

        # Load app preferences
        if hasattr(viewer, "load_preferences"):
            viewer.load_preferences(self._app.pref, True)

        # Set notebook and node, if requested
        if init == "current_node":
            old_viewer = self._current_viewer
            if old_viewer is not None and hasattr(old_viewer, "get_notebook"):
                viewer.set_notebook(old_viewer.get_notebook())
                node = old_viewer.get_current_node()
                if node:
                    viewer.goto_node(node)
        elif init == "none":
            pass
        else:
            raise Exception("unknown init")

        # Switch to the new tab
        self._tabs.set_current_page(self._tabs.get_n_pages() - 1)
        print("🧪 [TAB] viewer id:", id(viewer))
        print("🧪 [TAB] widget id:", id(widget), "widget type:", type(widget))
        print("🧪 [TAB] label id:", id(label), "label text:", label.get_text() if hasattr(label, "get_text") else "")

    def close_viewer(self, viewer):
        self.close_tab(self._tabs.page_num(viewer))

    def close_tab(self, pos=None):
        """Close a tab"""
        if self._tabs.get_n_pages() <= 1:
            return

        if pos is None:
            pos = self._tabs.get_current_page()
        viewer = self._tabs.get_nth_page(pos)

        # Clean up viewer
        viewer.set_notebook(None)
        for callid in self._callbacks[viewer]:
            viewer.disconnect(callid)
        del self._callbacks[viewer]
        del self._tab_names[viewer]
        self._main_window.remove_viewer(viewer)

        # Clean up UI
        if pos == self._tabs.get_current_page():
            viewer.remove_ui(self._main_window)
            self._current_viewer = None

        self._tabs.remove_page(pos)

    def _on_switch_tab(self, tabs, page, page_num):
        """Callback for switching between tabs"""
        if not self._ui_ready:
            self._current_viewer = self._tabs.get_nth_page(page_num)
            return

        if self._current_viewer:
            self._current_viewer.remove_ui(self._main_window)

        self._current_viewer = self._tabs.get_nth_page(page_num)
        self._current_viewer.add_ui(self._main_window)

        def func():
            self.emit("current-node", self._current_viewer.get_current_node())
            notebook = self._current_viewer.get_notebook()
            self.emit("modified", notebook.save_needed() if notebook else False)

        GLib.idle_add(func)

    def _on_tab_added(self, tabs, child, page_num):
        """Callback when a tab is added"""
        self._tabs.set_show_tabs(self._tabs.get_n_pages() > 1)

    def _on_tab_removed(self, tabs, child, page_num):
        """Callback when a tab is removed"""
        self._tabs.set_show_tabs(self._tabs.get_n_pages() > 1)

    def on_tab_current_node(self, viewer, node):
        """Callback for when a viewer wants to set its title"""
        if node is None:
            if viewer.get_notebook():
                title = viewer.get_notebook().get_attr("title", "")
                icon = None
            else:
                title = _("(Untitled)")
                icon = None
        else:
            title = node.get_attr("title", "")
            icon = get_node_icon(node, expand=False)

        MAX_TITLE = 20
        if len(title) > MAX_TITLE - 3:
            title = title[:MAX_TITLE - 3] + "..."

        tab = self._tabs.get_tab_label(viewer)
        if self._tab_names[viewer] is None:
            tab.set_text(title)
        tab.set_icon(icon)

        self.emit("current-node", node)

    def on_tab_modified(self, viewer, modified):
        """Callback for when viewer contains modified data"""
        self.emit("modified", modified)

    def switch_tab(self, step):
        """Switches to the next or previous tab"""
        pos = self._tabs.get_current_page()
        pos = (pos + step) % self._tabs.get_n_pages()
        self._tabs.set_current_page(pos)

    def _on_button_press(self, gesture, n_press, x, y):
        """Callback for double-click on tab bar"""
        if (self.get_toplevel().get_focus() == self._tabs and
                n_press == 2):  # Double-click
            label = self._tabs.get_tab_label(self._tabs.get_nth_page(self._tabs.get_current_page()))
            label.start_editing()
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def _on_new_tab_name(self, viewer, name):
        """Callback for when a tab gets a new name"""
        if name == "":
            name = None
        self._tab_names[viewer] = name
        if name is None:
            self.on_tab_current_node(viewer, viewer.get_current_node())

    # Viewer Methods
    def set_notebook(self, notebook):
        """Set the notebook for the viewer"""
        if notebook is None:
            return self._current_viewer.set_notebook(notebook)

        tabs = notebook.pref.get("viewers", "ids", self._viewerid, "tabs", default=[])
        if not tabs:
            if self._current_viewer.get_notebook():
                self.new_tab(init="none")
            return self._current_viewer.set_notebook(notebook)

        for tab in tabs:
            viewer_type = self._viewer_lookup.get1(tab.get("viewer_type", ""))
            viewer = self._current_viewer
            if viewer.get_notebook() or type(viewer) != viewer_type:
                viewer = viewer_type(self._app, self._main_window, tab.get("viewerid", None)) if viewer_type else None
                self.new_tab(viewer, init="none")
            else:
                viewer.set_id(tab.get("viewerid", None))

            viewer.set_notebook(notebook)
            name = tab.get("name", "")
            if name:
                self._tab_names[viewer] = name
                self._tabs.get_tab_label(viewer).set_text(name)

        current_id = notebook.pref.get("viewers", "ids", self._viewerid, "current_viewer", default="")
        for i, viewer in enumerate(self.iter_viewers()):
            if viewer.get_id() == current_id:
                self._tabs.set_current_page(i)
                break

    def get_notebook(self):
        page = self._tabs.get_nth_page(self._tabs.get_current_page())
        viewer = self._viewer_pages.get(page)
        if viewer is None:
            print("⚠️ get_notebook(): viewer not found for page")
            return None

        if viewer is not None and hasattr(viewer, "get_notebook"):
            return viewer.get_notebook()
        else:
            print("⚠️ get_notebook(): viewer not found or invalid")
            return None

    def close_notebook(self, notebook):
        closed_tabs = []
        for i, viewer in enumerate(self.iter_viewers()):
            notebook2 = viewer.get_notebook()
            viewer.close_notebook(notebook)
            if notebook2 is not None and viewer.get_notebook() is None:
                closed_tabs.append(i)

        for pos in reversed(closed_tabs):
            self.close_tab(pos)

    def load_preferences(self, app_pref, first_open=False):
        for widget in self._viewer_pages:
            viewer = self._viewer_pages[widget]
            if hasattr(viewer, "load_preferences"):
                viewer.load_preferences(app_pref, first_open)

    def save_preferences(self, app_pref):
        self._current_viewer.save_preferences(app_pref)

    def save(self):
        notebooks = set()
        for viewer in self.iter_viewers():
            viewer.save()
            notebook = viewer.get_notebook()
            if notebook:
                notebooks.add(notebook)

        for notebook in notebooks:
            tabs = notebook.pref.get("viewers", "ids", self._viewerid, "tabs", default=[])
            tabs[:] = []

        current_viewer = self._current_viewer
        for viewer in self.iter_viewers():
            notebook = viewer.get_notebook()
            if notebook:
                tabs = notebook.pref.get("viewers", "ids", self._viewerid, "tabs")
                name = self._tab_names[viewer]
                tabs.append({"viewer_type": viewer.get_name(), "viewerid": viewer.get_id(),
                             "name": name if name is not None else ""})
                if viewer == current_viewer:
                    notebook.pref.set("viewers", "ids", self._viewerid, "current_viewer", viewer.get_id())

    def undo(self):
        return self._current_viewer.undo()

    def redo(self):
        return self._current_viewer.redo()

    def get_editor(self):
        return self._current_viewer.get_editor()

    def new_node(self, kind, pos, parent=None):
        return self._current_viewer.new_node(kind, pos, parent)

    def get_current_node(self):
        return self._current_viewer.get_current_node()

    def get_selected_nodes(self):
        return self._current_viewer.get_selected_nodes()

    def goto_node(self, node, direct=False):
        return self._current_viewer.goto_node(node, direct)

    def visit_history(self, offset):
        self._current_viewer.visit_history(offset)

    def start_search_result(self):
        return self._current_viewer.start_search_result()

    def add_search_result(self, node):
        return self._current_viewer.add_search_result(node)

    def end_search_result(self):
        return self._current_viewer.end_search_result()

    def add_ui(self, window):
        assert window == self._main_window
        self._ui_ready = True
        # Note: Gtk.UIManager is deprecated in GTK 4, this needs reimplementation
        print("Warning: add_ui needs to be reimplemented for GTK 4 (Gtk.UIManager deprecated)")
        page = self._tabs.get_nth_page(self._tabs.get_current_page())
        viewer = self._viewer_pages.get(page)

        if viewer is not None and hasattr(viewer, "add_ui"):
            viewer.add_ui(window)
        else:
            print("⚠️ No valid viewer found for add_ui()")

    def remove_ui(self, window):
        assert window == self._main_window
        self._ui_ready = False
        self._current_viewer.remove_ui(window)
        # Note: Gtk.UIManager is deprecated in GTK 4, this needs reimplementation
        print("Warning: remove_ui needs to be reimplemented for GTK 4 (Gtk.UIManager deprecated)")

    def _get_ui(self):
        # Placeholder for GTK 4 GMenu or manual widget implementation
        print("Warning: _get_ui needs to be reimplemented for GTK 4")
        return []

    def _get_actions(self):
        return [Action(*x) for x in [
            ("New Tab", None, _("New _Tab"), "<shift><control>T", _("Open a new tab"), lambda w: self.new_tab()),
            ("Close Tab", None, _("Close _Tab"), "<shift><control>W", _("Close a tab"), lambda w: self.close_tab()),
            ("Next Tab", None, _("_Next Tab"), "<control>Page_Down", _("Switch to next tab"),
             lambda w: self.switch_tab(1)),
            ("Previous Tab", None, _("_Previous Tab"), "<control>Page_Up", _("Switch to previous tab"),
             lambda w: self.switch_tab(-1))
        ]]



class TabLabel(Gtk.Box):
    __gsignals__ = {
        "new-name": (GObject.SIGNAL_RUN_LAST, None, (str,)),
    }

    def __init__(self, tabs, viewer, icon, text):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        self.tabs = tabs
        self.viewer = viewer

        # Icon
        self.icon = Gtk.Image()
        if icon:
            self.icon.set_from_pixbuf(icon)
        self.icon.set_visible(True)  # Replaces show()

        # Label
        self.label = Gtk.Label(label=text)
        self.label.set_halign(Gtk.Align.START)
        self.label.set_valign(Gtk.Align.CENTER)
        self.label.set_visible(True)  # Replaces show()

        # Entry
        self.entry = Gtk.Entry()
        self.entry.set_halign(Gtk.Align.START)

        # Replace "focus-out-event" with EventControllerFocus
        focus_controller = Gtk.EventControllerFocus.new()
        focus_controller.connect("leave", lambda controller: self.stop_editing())
        self.entry.add_controller(focus_controller)

        self.entry.connect("activate", self._done)
        self._editing = False

        # Close button with hover effects using EventControllerMotion
        self.eclose_button = Gtk.Box()
        self.close_button = keepnote.gui.get_resource_image("close_tab.png")
        self.eclose_button.append(self.close_button)  # Changed from add to set_child
        self.eclose_button.set_visible(True)  # Replaces show()
        self.close_button.set_visible(True)  # Replaces show()

        # Replace "enter-notify-event" and "leave-notify-event" with EventControllerMotion
        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("enter",
                                  lambda controller, x, y: self.close_button.set_state_flags(Gtk.StateFlags.PRELIGHT,
                                                                                             clear=False))
        motion_controller.connect("leave", lambda controller: self.close_button.set_state_flags(Gtk.StateFlags.NORMAL,
                                                                                                clear=True))
        self.eclose_button.add_controller(motion_controller)

        # Replace "button-press-event" with GestureClick
        click_controller = Gtk.GestureClick.new()
        click_controller.set_button(1)  # Left-click
        click_controller.connect("pressed", lambda gesture, n_press, x, y: self.tabs.close_viewer(self.viewer))
        self.eclose_button.add_controller(click_controller)

        # Layout
        self.append(self.icon)  # Changed from pack_start to append
        self.append(self.label)  # Changed from pack_start to append
        self.append(self.eclose_button)  # Changed from pack_start to append

    def _done(self, widget):
        text = self.entry.get_text()
        self.stop_editing()
        self.label.set_label(text)
        self.emit("new-name", text)

    def start_editing(self):
        if not self._editing:
            self._editing = True
            # In GTK 4, get_preferred_size() is replaced with measure()
            width = self.label.measure(Gtk.Orientation.HORIZONTAL, -1)[1]  # Minimum width
            height = self.label.measure(Gtk.Orientation.VERTICAL, -1)[1]  # Minimum height
            self.remove(self.label)
            self.entry.set_text(self.label.get_label())
            self.append(self.entry)  # Changed from pack_start to append
            self.reorder_child(self.entry, 1)
            self.entry.set_size_request(int(width), int(height))
            self.entry.set_visible(True)  # Replaces show()
            self.entry.grab_focus()

    def stop_editing(self):
        if self._editing:
            self._editing = False
            self.remove(self.entry)
            self.append(self.label)  # Changed from pack_start to append
            self.reorder_child(self.label, 1)
            self.label.set_visible(True)  # Replaces show()

    def set_text(self, text):
        if not self._editing:
            self.label.set_text(text)

    def set_icon(self, pixbuf):
        self.icon.set_from_pixbuf(pixbuf)




GObject.type_register(TabLabel)
# GObject.signal_new("new-name", TabLabel, GObject.SignalFlags.RUN_LAST, None, (str,))