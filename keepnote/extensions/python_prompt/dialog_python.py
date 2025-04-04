import sys
import gi
gi.require_version('Gtk', '4.0')
# PyGObject imports
from gi.repository import Gtk, Gdk, Pango

# KeepNote imports
import keepnote
from keepnote.gui import Action


def move_to_start_of_line(it):
    """Move a TextIter to the start of a paragraph"""
    if not it.starts_line():
        if it.get_line() > 0:
            it.backward_line()
            it.forward_line()
        else:
            it = it.get_buffer().get_start_iter()
    return it


def move_to_end_of_line(it):
    """Move a TextIter to the start of a paragraph"""
    it.forward_line()
    return it


class Stream:
    def __init__(self, callback):
        self._callback = callback

    def write(self, text):
        self._callback(text)

    def flush(self):
        pass


class PythonDialog:
    """Python dialog for KeepNote using PyGObject (GTK 4)"""

    def __init__(self, main_window):
        self.main_window = main_window
        self.app = main_window.get_app()

        self.outfile = Stream(self.output_text)
        self.errfile = Stream(lambda t: self.output_text(t, "error"))

        # Create text tags for styling
        self.error_tag = Gtk.TextTag.new("error")
        self.error_tag.set_property("foreground", "red")
        self.error_tag.set_property("weight", Pango.Weight.BOLD)

        self.info_tag = Gtk.TextTag.new("info")
        self.info_tag.set_property("foreground", "blue")
        self.info_tag.set_property("weight", Pango.Weight.BOLD)

    def show(self):
        # Setup environment
        self.env = {"app": self.app, "window": self.main_window, "info": self.print_info}

        # Create dialog
        self.dialog = Gtk.Window()
        self.dialog.connect("close-request", lambda d: self.dialog.destroy())
        self.dialog.set_default_size(400, 400)
        self.dialog.ptr = self  # Store reference (unchanged from original)

        # Vertical paned layout
        self.vpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.dialog.set_child(self.vpaned)
        self.vpaned.set_position(200)

        # Editor buffer
        self.editor = Gtk.TextView()
        self.editor.connect("key-press-event", self.on_key_press_event)
        # Set font using CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data("""
        * {
            font-family: "Courier New", monospace;
            font-size: 10pt;
        }
        """.encode('utf-8'))
        self.editor.add_css_class("monospace")
        self.editor.get_style_context().add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_has_frame(True)
        sw.set_child(self.editor)
        self.vpaned.set_start_child(sw)
        self.vpaned.set_resize_start_child(True)

        # Output buffer
        self.output = Gtk.TextView()
        self.output.set_wrap_mode(Gtk.WrapMode.WORD)
        # Set font using CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data("""
        * {
            font-family: "Courier New", monospace;
            font-size: 10pt;
        }
        """.encode('utf-8'))
        self.output.add_css_class("monospace")
        self.output.get_style_context().add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_has_frame(True)
        sw.set_child(self.output)
        self.vpaned.set_end_child(sw)
        self.vpaned.set_resize_end_child(True)

        # Add tags to output buffer's tag table
        tag_table = self.output.get_buffer().get_tag_table()
        tag_table.add(self.error_tag)
        tag_table.add(self.info_tag)

        # Show dialog
        self.dialog.present()
        self.output_text("Press Ctrl+Enter to execute. Ready...\n", "info")

    def on_key_press_event(self, textview, event):
        """Callback for key press events"""
        keyval = event.get_keyval()[1]  # GTK 4 returns a tuple (success, keyval)
        state = event.get_state()

        if keyval == Gdk.KEY_Return and state & Gdk.ModifierType.CONTROL_MASK:
            # Execute code on Ctrl+Enter
            self.execute_buffer()
            return True

        if keyval == Gdk.KEY_Return:
            # New line indenting
            self.newline_indent()
            return True

        return False

    def newline_indent(self):
        """Insert a newline and indent"""
        buf = self.editor.get_buffer()
        insert_mark = buf.get_insert()
        it = buf.get_iter_at_mark(insert_mark)
        start = move_to_start_of_line(it.copy())
        line = buf.get_text(start, it, include_hidden_chars=False)
        indent = "".join(c for c in line if c in " \t")
        buf.insert_at_cursor("\n" + indent)

    def execute_buffer(self):
        """Execute code in buffer"""
        buf = self.editor.get_buffer()
        sel = buf.get_selection_bounds()

        if sel:
            start, end = sel
            self.output_text("executing selection:\n", "info")
        else:
            start = buf.get_start_iter()
            end = buf.get_end_iter()
            self.output_text("executing buffer:\n", "info")

        text = buf.get_text(start, end, include_hidden_chars=False)
        execute(text, self.env, self.outfile, self.errfile)

    def output_text(self, text, mode="normal"):
        """Output text to output buffer"""
        buf = self.output.get_buffer()
        insert_mark = buf.get_insert()
        it = buf.get_iter_at_mark(insert_mark)
        follow = it.is_end()

        end_iter = buf.get_end_iter()
        if mode == "error":
            buf.insert_with_tags(end_iter, text, self.error_tag)
        elif mode == "info":
            buf.insert_with_tags(end_iter, text, self.info_tag)
        else:
            buf.insert(end_iter, text)

        if follow:
            buf.place_cursor(buf.get_end_iter())
            self.output.scroll_to_mark(insert_mark, 0.0, True, 0.0, 1.0)

    def print_info(self):
        """Print runtime information"""
        print("COMMON INFORMATION")
        print("==================")
        print()
        keepnote.print_runtime_info(sys.stdout)
        print("Open notebooks")
        print("--------------")
        print("\n".join(n.get_path() for n in self.app.iter_notebooks()))


def execute(code, vars, stdout, stderr):
    """Execute user's Python code"""
    __stdout = sys.stdout
    __stderr = sys.stderr
    sys.stdout = stdout
    sys.stderr = stderr
    try:
        exec(code, vars)
    except Exception as e:
        keepnote.log_error(e, sys.exc_info()[2], stderr)
    sys.stdout = __stdout
    sys.stderr = __stderr


# Ensure this file can be imported as an extension
if __name__ == "__main__":
    # Example usage (not typically run standalone)
    from keepnote.gui import KeepNote
    app = KeepNote()
    win = app.new_window()
    dialog = PythonDialog(win)
    dialog.show()
    app.run()