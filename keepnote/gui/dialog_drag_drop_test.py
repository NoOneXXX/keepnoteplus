# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
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
        self.drag_win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.drag_win.connect("delete-event", lambda w, e: self.drag_win.destroy())
        self.drag_win.drag_dest_set(0, [], Gdk.DragAction.DEFAULT)

        self.drag_win.set_default_size(400, 400)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.drag_win.add(vbox)

        self.drag_win.mime = Gtk.TextView()
        vbox.pack_start(self.drag_win.mime, False, True, 0)

        self.drag_win.editor = Gtk.TextView()
        self.drag_win.editor.connect("drag-motion", self.on_drag_and_drop_test_motion)
        self.drag_win.editor.connect("drag-data-received", self.on_drag_and_drop_test_data)
        self.drag_win.editor.connect("paste-clipboard", self.on_drag_and_drop_test_paste)
        self.drag_win.editor.set_wrap_mode(Gtk.WrapMode.WORD)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.drag_win.editor)
        vbox.pack_start(sw, True, True, 0)

        self.drag_win.show_all()

    def on_drag_and_drop_test_motion(self, textview, drag_context, x, y, timestamp):
        buf = self.drag_win.mime.get_buffer()
        target = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if target != "":
            # In GTK 3, we need to create a list of Gdk.Atom objects for the target list
            target_list = Gtk.TargetList.new([])
            target_list.add(Gdk.Atom.intern(target, False), 0, 0)
            textview.drag_dest_set_target_list(target_list)

    def on_drag_and_drop_test_data(self, textview, drag_context, x, y, selection_data, info, eventtime):
        # In GTK 3, drag_context.targets is a list of Gdk.Atom objects
        targets = [atom.name() for atom in drag_context.list_targets()]
        textview.get_buffer().insert_at_cursor(f"drag_context = {targets}\n")

        # Stop the signal emission
        textview.stop_emission_by_name("drag-data-received")

        buf = textview.get_buffer()
        data = selection_data.get_data()
        buf.insert_at_cursor(f"type(sel.data) = {type(data)}\n")
        buf.insert_at_cursor(f"sel.data = {repr(data)[:1000]}\n")
        drag_context.finish(False, False, eventtime)

    def on_drag_and_drop_test_paste(self, textview):
        clipboard = self.main_window.get_clipboard(selection=Gdk.SELECTION_CLIPBOARD)
        targets = clipboard.wait_for_targets()
        textview.get_buffer().insert_at_cursor(f"clipboard.targets = {[atom.name() for atom in targets]}\n")
        textview.stop_emission_by_name("paste-clipboard")

        buf = self.drag_win.mime.get_buffer()
        target = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if target != "":
            clipboard.request_contents(Gdk.Atom.intern(target, False), self.on_drag_and_drop_test_contents)

    def on_drag_and_drop_test_contents(self, clipboard, selection_data, data):
        buf = self.drag_win.editor.get_buffer()
        data = selection_data.get_data()
        targets = selection_data.get_targets()
        buf.insert_at_cursor(f"sel.targets = {[atom.name() for atom in targets]}\n")
        buf.insert_at_cursor(f"type(sel.data) = {type(data)}\n")
        print(f"sel.data = {repr(data)[:1000]}\n")
        buf.insert_at_cursor(f"sel.data = {repr(data)[:5000]}\n")