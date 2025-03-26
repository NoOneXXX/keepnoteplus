# PyGObject imports
from gi import require_version
require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk


class PopupWindow(Gtk.Window):
    """A customizable popup window"""

    def __init__(self, parent):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_type_hint(Gdk.WindowTypeHint.MENU)
        self.set_transient_for(parent.get_toplevel())
        self.set_can_focus(True)
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK |
                        Gdk.EventMask.KEY_RELEASE_MASK)

        self._parent = parent
        self._parent.get_toplevel().connect("configure-event",
                                            self._on_configure_event)

        # Coordinates of popup
        self._x = 0
        self._y = 0
        self._y2 = 0

    def _on_configure_event(self, widget, event):
        self.move_on_parent(self._x, self._y, self._y2)

    def move_on_parent(self, x, y, y2):
        """Move popup relative to parent widget"""

        win = self._parent.get_parent_window()
        if win is None:
            return

        # Remember coordinates
        self._x = x
        self._y = y
        self._y2 = y2

        # Get screen dimensions
        screen = self.get_screen()
        screenh = screen.get_height()

        # Account for window
        wx, wy = win.get_origin()

        # Account for widget
        rect = self._parent.get_allocation()
        x3 = wx + rect.x
        y3 = wy + rect.y

        # Get size of popup
        child = self.get_child()
        if child:
            w, h = child.get_preferred_size()[1].width, child.get_preferred_size()[1].height
            self.resize(w, h)

        # Perform move
        if y + y3 + h < screenh:
            # Drop down
            self.move(x + x3, y + y3)
        else:
            # Drop up
            self.move(x + x3, y2 + y3 - h)