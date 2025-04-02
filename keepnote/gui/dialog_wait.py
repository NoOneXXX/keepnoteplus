# Python 3 and PyGObject imports
import time
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
from gi.repository import Gtk, GLib

# KeepNote imports
import keepnote
from keepnote import get_resource

class WaitDialog:
    def __init__(self, parent_window):
        self.parent_window = parent_window
        self._task = None
        self.xml = None
        self.dialog = None
        self.text = None
        self.progressbar = None

    def show(self, title, message, task, cancel=True):
        # Load the Glade file
        self.xml = Gtk.Builder()
        self.xml.add_from_file(get_resource("rc", "keepnote.glade"))
        self.xml.set_translation_domain(keepnote.GETTEXT_DOMAIN)
        self.dialog = self.xml.get_object("wait_dialog")
        self.dialog.connect("delete-event", self._on_close)
        self.dialog.set_transient_for(self.parent_window)

        # Get widgets
        self.text = self.xml.get_object("wait_text_label")
        self.progressbar = self.xml.get_object("wait_progressbar")

        # Connect signals
        self.xml.connect_signals(self)

        # 添加检查
        content_area = self.dialog.get_content_area()
        children = content_area.get_children()
        if len(children) > 1:
            print(f"Warning: WaitDialog has multiple children: {children}")
            for child in children[1:]:
                content_area.remove(child)

        # Set initial values
        self.dialog.set_title(title)
        self.text.set_text(message)
        self._task = task
        self._task.change_event.add(self._on_task_update)

        # Enable/disable cancel button
        cancel_button = self.xml.get_object("wait_cancel_button")
        cancel_button.set_sensitive(cancel)

        # Show the dialog and start the task
        self.dialog.show()
        self._task.run()
        self._on_idle()
        self.dialog.run()
        self._task.join()

        # Clean up
        self._task.change_event.remove(self._on_task_update)

    def _on_idle(self):
        """Idle function to update the UI"""
        lasttime = [time.time()]
        pulse_rate = 0.5  # Seconds per sweep
        update_rate = 100  # Milliseconds

        def gui_update():
            # Close dialog if task is stopped
            if self._task.is_stopped():
                self.dialog.destroy()
                return False  # Stop the timeout

            # Update progress bar
            percent = self._task.get_percent()
            if percent is None:
                t = time.time()
                timestep = t - lasttime[0]
                lasttime[0] = t
                step = max(min(timestep / pulse_rate, 0.1), 0.001)
                self.progressbar.set_pulse_step(step)
                self.progressbar.pulse()
            else:
                self.progressbar.set_fraction(percent)

            # Filter for messages we process
            messages = [x for x in self._task.get_messages() if isinstance(x, tuple) and len(x) == 2]
            texts = [a_b for a_b in messages if a_b[0] == "text"]
            details = [a_b for a_b in messages if a_b[0] == "detail"]

            # Update text
            if texts:
                self.text.set_text(texts[-1][1])
            if details:
                self.progressbar.set_text(details[-1][1])

            return True  # Continue the timeout

        # Use GLib.timeout_add instead of gobject.timeout_add
        GLib.timeout_add(update_rate, gui_update)

    def _on_task_update(self):
        """Callback for task updates (currently a no-op)"""
        pass

    def _on_close(self, window, event):
        """Handle dialog close event"""
        self._task.stop()
        return True  # Prevent default close behavior

    def on_cancel_button_clicked(self, button):
        """Attempt to stop the task when the cancel button is clicked"""
        self.text.set_text("Canceling...")
        self._task.stop()