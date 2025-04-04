# Python 3 and PyGObject imports
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk

# KeepNote imports (assuming the keepnote module is available)
import keepnote


def parse_utf(text):
    """Parse UTF-encoded text (UTF-8 or UTF-16)."""
    if isinstance(text, bytes):
        if (text[:2] in (b'\xff\xfe', b'\xfe\xff') or
                (len(text) > 1 and text[1] == 0) or
                (len(text) > 3 and text[3] == 0)):
            return text.decode("utf-16")
        else:
            return text.decode("utf-8")
    return text


class DragDropTestDialog:
    """Drag and drop testing dialog"""

    def __init__(self, main_window):
        self.main_window = main_window

    def on_drag_and_drop_test(self):
        self.drag_win = Gtk.Window()
        self.drag_win.connect("close-request", lambda w: self.drag_win.destroy())
        self.drag_win.set_default_size(400, 400)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.drag_win.set_child(vbox)

        self.drag_win.mime = Gtk.TextView()
        vbox.append(self.drag_win.mime)

        self.drag_win.editor = Gtk.TextView()
        self.drag_win.editor.set_wrap_mode(Gtk.WrapMode.WORD)

        # Set up drag and drop with Gtk.DropTarget
        drop_target = Gtk.DropTarget.new(str, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        drop_target.connect("motion", self.on_drag_and_drop_test_motion)
        drop_target.connect("drop", self.on_drag_and_drop_test_drop)
        self.drag_win.editor.add_controller(drop_target)

        # Connect paste clipboard signal
        self.drag_win.editor.connect("paste-clipboard", self.on_drag_and_drop_test_paste)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(self.drag_win.editor)
        vbox.append(sw)

        self.drag_win.show()

    def on_drag_and_drop_test_motion(self, drop_target, x, y):
        buf = self.drag_win.mime.get_buffer()
        target = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if target != "":
            # In GTK 4, DropTarget accepts a single type or None; adjust dynamically if needed
            drop_target.set_gtypes([str])  # We expect string data
        return Gdk.DragAction.COPY  # Indicate we can accept the drop

    def on_drag_and_drop_test_drop(self, drop_target, value, x, y):
        # In GTK 4, drop data is passed directly as a value
        textview = self.drag_win.editor
        buf = textview.get_buffer()

        # Get formats from the drop target
        formats = drop_target.get_formats()
        targets = [fmt for fmt in formats.get_content_types()]  # Get list of mime types
        buf.insert_at_cursor(f"drop formats = {targets}\n")

        # Handle the dropped data
        data = value if isinstance(value, str) else str(value)  # Ensure string data
        buf.insert_at_cursor(f"type(value) = {type(value)}\n")
        buf.insert_at_cursor(f"value = {repr(data)[:1000]}\n")

        # No need for drag_context.finish in GTK 4; DropTarget handles it
        return True  # Indicate drop was successful

    def on_drag_and_drop_test_paste(self, textview):
        clipboard = Gtk.Clipboard.get_default(self.main_window.get_display())

        # In GTK 4, clipboard handling is async; use read_text_async
        def on_clipboard_text(clipboard, result):
            text = clipboard.read_text_finish(result)
            buf = self.drag_win.editor.get_buffer()
            buf.insert_at_cursor(f"clipboard.text = {repr(text)[:1000]}\n")
            buf.insert_at_cursor(f"type(text) = {type(text)}\n")

        buf = self.drag_win.mime.get_buffer()
        target = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if target != "":
            clipboard.read_text_async(None, on_clipboard_text)

        # Stop emission not needed in GTK 4 for this case, but we can prevent default paste
        return True

    def on_drag_and_drop_test_contents(self, clipboard, result, data):
        # This method is no longer directly used due to async clipboard in GTK 4
        # Handled in on_clipboard_text callback above
        pass


if __name__ == "__main__":
    # Minimal test setup (requires a mock main_window)
    class MockWindow:
        def get_display(self):
            return Gdk.Display.get_default()

        def get_clipboard(self, selection=None):
            return Gtk.Clipboard.get_default(Gdk.Display.get_default())


    win = MockWindow()
    dialog = DragDropTestDialog(win)
    dialog.on_drag_and_drop_test()
    Gtk.main()