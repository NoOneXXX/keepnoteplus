# PyGObject imports
from gi import require_version
require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk

class PopupWindow(Gtk.Window):
    """A customizable popup window"""

    def __init__(self, parent):
        super().__init__(type_hint=Gdk.SurfaceTypeHint.MENU)  # Replaces WindowType.POPUP and set_type_hint
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

        win = self._parent.get_parent_surface()  # Replaces get_parent_window
        if win is None:
            return

        # Remember coordinates
        self._x = x
        self._y = y
        self._y2 = y2

        # Get screen dimensions
        display = self.get_display()
        monitor = display.get_monitor_at_surface(win)
        geometry = monitor.get_geometry()
        screenh = geometry.height  # Replaces screen.get_height()

        # Account for window
        wx, wy = win.get_position()  # Replaces get_origin()

        # Account for widget
        rect = self._parent.get_allocation()
        x3 = wx + rect.x
        y3 = wy + rect.y

        # Get size of popup
        child = self.get_child()
        if child:
            # In GTK 4, get_preferred_size() is replaced with measure()
            child.measure(Gtk.Orientation.HORIZONTAL, -1)
            child.measure(Gtk.Orientation.VERTICAL, -1)
            w = child.get_width()  # Simplified for now
            h = child.get_height()  # Simplified for now
            self.set_default_size(w, h)  # Replaces resize()

        # Perform move
        if y + y3 + h < screenh:
            # Drop down
            self.set_position(x + x3, y + y3)  # Replaces move()
        else:
            # Drop up
            self.set_position(x + x3, y2 + y3 - h)  # Replaces move()

    def set_position(self, x, y):
        """Set the position of the window"""
        # In GTK 4, move() is replaced with manual positioning
        self.set_default_position(x, y)  # Custom method to store position
        if self.get_realized():
            self.get_surface().move(x, y)

    def set_default_position(self, x, y):
        """Store the default position for unrealized windows"""
        self._default_x = x
        self._default_y = y

    def realize(self):
        """Override realize to set position after realization"""
        super().realize()
        if hasattr(self, '_default_x') and hasattr(self, '_default_y'):
            self.get_surface().move(self._default_x, self._default_y)