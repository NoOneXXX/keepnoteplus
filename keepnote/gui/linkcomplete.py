# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
from gi.repository import Gtk, GObject, Gdk, GdkPixbuf

# KeepNote imports
from keepnote import unicode_gtk
from keepnote.gui.popupwindow import PopupWindow

class LinkPicker(Gtk.TreeView):
    """A TreeView for displaying and selecting links"""

    def __init__(self, maxwidth=450):
        super().__init__()
        self._maxwidth = maxwidth

        self.set_headers_visible(False)

        # Add column
        self.column = Gtk.TreeViewColumn()
        self.append_column(self.column)

        # Create cell renderers
        self.cell_icon = Gtk.CellRendererPixbuf()
        self.cell_text = Gtk.CellRendererText()

        # Add the cells to the column
        self.column.pack_start(self.cell_icon, False)
        self.column.pack_start(self.cell_text, True)

        # Map cells to columns in the treestore
        self.column.add_attribute(self.cell_icon, 'pixbuf', 0)
        self.column.add_attribute(self.cell_text, 'text', 1)

        # Create a ListStore for pixbuf, text, and nodeid
        self.list = Gtk.ListStore(GdkPixbuf.Pixbuf, str, object)
        self.set_model(self.list)

        self.maxlinks = 10

    def set_links(self, urls):
        """Set the links to display in the TreeView"""
        self.list.clear()
        for nodeid, url, icon in urls[:self.maxlinks]:
            self.list.append([icon, url, nodeid])

        self.column.queue_resize()

        # Adjust size based on content
        w, h = self.get_preferred_size()[1].width, self.get_preferred_size()[1].height
        if w > self._maxwidth:
            self.set_size_request(self._maxwidth, -1)
        else:
            self.set_size_request(-1, -1)

class LinkPickerPopup(PopupWindow):
    """A popup window for selecting links using LinkPicker"""

    def __init__(self, parent, maxwidth=100):
        super().__init__(parent)
        self._maxwidth = maxwidth

        self._link_picker = LinkPicker()
        self._link_picker.show()
        self._link_picker.get_selection().connect("changed", self.on_select_changed)
        self._cursor_move = False

        self._shown = False

        # Use frame for border
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        frame.add(self._link_picker)
        frame.show()
        self.add(frame)

    def set_links(self, urls):
        """Set links in popup"""
        self._link_picker.set_links(urls)

        if len(urls) == 0:
            self.hide()
            self._shown = False
        else:
            self.show()
            self._shown = True

    def shown(self):
        """Return True if popup is visible"""
        return self._shown

    def on_key_press_event(self, widget, event):
        """Callback for key press events"""
        model, sel = self._link_picker.get_selection().get_selected()

        if event.keyval == Gdk.KEY_Down:
            # Move selection down
            self._cursor_move = True

            if sel is None:
                self._link_picker.set_cursor((0,))
            else:
                i = model.get_path(sel)[0]
                n = model.iter_n_children(None)
                if i < n - 1:
                    self._link_picker.set_cursor((i + 1,))

            return True

        elif event.keyval == Gdk.KEY_Up:
            # Move selection up
            self._cursor_move = True

            if sel is None:
                n = model.iter_n_children(None)
                self._link_picker.set_cursor((n - 1,))
            else:
                i = model.get_path(sel)[0]
                if i > 0:
                    self._link_picker.set_cursor((i - 1,))

            return True

        elif event.keyval == Gdk.KEY_Return:
            # Accept selection
            if sel:
                icon, title, nodeid = model[sel]
                self.emit("pick-link", title, nodeid)
                return True

        elif event.keyval == Gdk.KEY_Escape:
            # Discard popup
            self.set_links([])

        return False

    def on_select_changed(self, treeselect):
        """Callback for selection changes"""
        if not self._cursor_move:
            model, sel = self._link_picker.get_selection().get_selected()
            if sel:
                icon, title, nodeid = model[sel]
                self.emit("pick-link", title, nodeid)

        self._cursor_move = False

# Register the custom signal for LinkPickerPopup
GObject.type_register(LinkPickerPopup)
GObject.signal_new("pick-link", LinkPickerPopup, GObject.SignalFlags.RUN_LAST,
                   None, (str, object))