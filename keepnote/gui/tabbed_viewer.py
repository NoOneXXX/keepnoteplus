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
        self._default_viewer = default_viewer
        self._current_viewer = None
        self._callbacks = {}
        self._ui_ready = False
        self._null_viewer = Viewer(app, main_window)
        self._tab_names = {}

        # Viewer registry
        self._viewer_lookup = TwoWayDict()
        self._viewer_lookup.add(ThreePaneViewer(app, main_window).get_name(), ThreePaneViewer)

        # Layout
        self._tabs = Gtk.Notebook()
        self._tabs.show()
        self._tabs.set_show_border(False)
        # Remove this line: self._tabs.set_property("homogeneous", True)
        self._tabs.set_scrollable(True)
        self._tabs.connect("switch-page", self._on_switch_tab)
        self._tabs.connect("page-added", self._on_tab_added)
        self._tabs.connect("page-removed", self._on_tab_removed)
        self._tabs.connect("button-press-event", self._on_button_press)
        self.pack_start(self._tabs, True, True, 0)

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
        if viewer is None:
            viewer = self._default_viewer(self._app, self._main_window)
        label = TabLabel(self, viewer, None, _("(Untitled)"))
        label.connect("new-name", lambda w, text: self._on_new_tab_name(viewer, text))
        self._tabs.append_page(viewer, label)
        self._tabs.set_tab_reorderable(viewer, True)
        self._tab_names[viewer] = None
        viewer.show_all()

        # Setup viewer signals
        self._callbacks[viewer] = [
            viewer.connect("error", lambda w, m, e: self.emit("error", m, e)),
            viewer.connect("status", lambda w, m, b: self.emit("status", m, b)),
            viewer.connect("window-request", lambda w, t: self.emit("window-request", t)),
            viewer.connect("current-node", self.on_tab_current_node),
            viewer.connect("modified", self.on_tab_modified)
        ]

        # Load app preferences
        viewer.load_preferences(self._app.pref, True)

        # Set notebook and node, if requested
        if init == "current_node":
            old_viewer = self._current_viewer
            if old_viewer is not None:
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
            title = title[:MAX_TITLE-3] + "..."

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

    def _on_button_press(self, widget, event):
        if (self.get_toplevel().get_focus() == self._tabs and
                event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS):
            label = self._tabs.get_tab_label(self._tabs.get_nth_page(self._tabs.get_current_page()))
            label.start_editing()

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
        return self._current_viewer.get_notebook()

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
        for viewer in self.iter_viewers():
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
                tabs.append({"viewer_type": viewer.get_name(), "viewerid": viewer.get_id(), "name": name if name is not None else ""})
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
        self._action_group = Gtk.ActionGroup(name="Tabbed Viewer")
        self._uis = []
        add_actions(self._action_group, self._get_actions())
        self._main_window.get_uimanager().insert_action_group(self._action_group, 0)
        for s in self._get_ui():
            self._uis.append(self._main_window.get_uimanager().add_ui_from_string(s))
        self._current_viewer.add_ui(window)

    def remove_ui(self, window):
        assert window == self._main_window
        self._ui_ready = False
        self._current_viewer.remove_ui(window)
        for ui in reversed(self._uis):
            self._main_window.get_uimanager().remove_ui(ui)
        self._uis = []
        self._main_window.get_uimanager().remove_action_group(self._action_group)

    def _get_ui(self):
        return ["""
<ui>
<!-- main window menu bar -->
<menubar name="main_menu_bar">
  <menu action="Go">
    <placeholder name="Viewer">
      <menuitem action="Next Tab"/>
      <menuitem action="Previous Tab"/>
      <separator/>
    </placeholder>
  </menu>
  <menu action="Window">
    <placeholder name="Viewer Window">
      <menuitem action="New Tab"/>
      <menuitem action="Close Tab"/>
    </placeholder>
  </menu>
</menubar>
</ui>
"""]

    def _get_actions(self):
        return [Action(*x) for x in [
            ("New Tab", None, _("New _Tab"), "<shift><control>T", _("Open a new tab"), lambda w: self.new_tab()),
            ("Close Tab", None, _("Close _Tab"), "<shift><control>W", _("Close a tab"), lambda w: self.close_tab()),
            ("Next Tab", None, _("_Next Tab"), "<control>Page_Down", _("Switch to next tab"), lambda w: self.switch_tab(1)),
            ("Previous Tab", None, _("_Previous Tab"), "<control>Page_Up", _("Switch to previous tab"), lambda w: self.switch_tab(-1))
        ]]


class TabLabel(Gtk.Box):
    def __init__(self, tabs, viewer, icon, text):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        self.tabs = tabs
        self.viewer = viewer

        # Icon
        self.icon = Gtk.Image()
        if icon:
            self.icon.set_from_pixbuf(icon)
        self.icon.show()

        # Label
        self.label = Gtk.Label(label=text)
        self.label.set_halign(Gtk.Align.START)
        self.label.set_valign(Gtk.Align.CENTER)
        self.label.show()

        # Entry
        self.entry = Gtk.Entry()
        self.entry.set_halign(Gtk.Align.START)
        self.entry.connect("focus-out-event", lambda w, e: self.stop_editing())
        self.entry.connect("activate", self._done)
        self._editing = False

        # Close button
        self.close_button_state = [Gtk.StateType.NORMAL]

        def highlight(w, state):
            self.close_button_state[0] = w.get_state()
            w.set_state(state)

        self.eclose_button = Gtk.EventBox()
        self.close_button = keepnote.gui.get_resource_image("close_tab.png")
        self.eclose_button.add(self.close_button)
        self.eclose_button.show()

        self.eclose_button.connect("enter-notify-event", lambda w, e: highlight(w, Gtk.StateType.PRELIGHT))
        self.eclose_button.connect("leave-notify-event", lambda w, e: highlight(w, self.close_button_state[0]))
        self.close_button.show()

        self.eclose_button.connect("button-press-event", lambda w, e:
                                   self.tabs.close_viewer(self.viewer) if e.button == 1 else None)

        # Layout
        self.pack_start(self.icon, False, False, 0)
        self.pack_start(self.label, True, True, 0)
        self.pack_start(self.eclose_button, False, False, 0)

    def _done(self, widget):
        text = self.entry.get_text()
        self.stop_editing()
        self.label.set_label(text)
        self.emit("new-name", text)

    def start_editing(self):
        if not self._editing:
            self._editing = True
            size = self.label.get_preferred_size()
            w, h = size[1].width, size[1].height
            self.remove(self.label)
            self.entry.set_text(self.label.get_label())
            self.pack_start(self.entry, True, True, 0)
            self.reorder_child(self.entry, 1)
            self.entry.set_size_request(w, h)
            self.entry.show()
            self.entry.grab_focus()

    def stop_editing(self):
        if self._editing:
            self._editing = False
            self.remove(self.entry)
            self.pack_start(self.label, True, True, 0)
            self.reorder_child(self.label, 1)
            self.label.show()

    def set_text(self, text):
        if not self._editing:
            self.label.set_text(text)

    def set_icon(self, pixbuf):
        self.icon.set_from_pixbuf(pixbuf)


GObject.type_register(TabLabel)
GObject.signal_new("new-name", TabLabel, GObject.SignalFlags.RUN_LAST, None, (str,))