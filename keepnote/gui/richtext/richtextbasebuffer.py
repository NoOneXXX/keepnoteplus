"""
KeepNote
Richtext buffer base class
"""
import gi
gi.require_version('Gtk', '3.0')
# PyGObject imports (GTK 3)
from gi.repository import Gtk, GObject

# Import textbuffer tools
from .textbuffer_tools import \
    get_paragraph

from .undo_handler import \
    UndoHandler, \
    InsertAction, \
    DeleteAction, \
    InsertChildAction

# RichText imports
from .richtextbase_tags import \
    RichTextBaseTagTable, \
    RichTextTag

def add_child_to_buffer(textbuffer, it, anchor):
    textbuffer.add_child(it, anchor)

# RichTextAnchor class
class RichTextAnchor(Gtk.TextChildAnchor):
    """Base class of all anchor objects in a RichTextView"""
    __gsignals__ = {
        "selected": (GObject.SIGNAL_RUN_LAST, None, ()),
        "activated": (GObject.SIGNAL_RUN_LAST, None, ()),
        "popup-menu": (GObject.SIGNAL_RUN_LAST, None, (int, object)),
        "init": (GObject.SIGNAL_RUN_LAST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self._widgets = {}
        self._buffer = None

    def add_view(self, view):
        return None

    def get_widget(self, view=None):
        return self._widgets[view]

    def get_all_widgets(self):
        return self._widgets

    def show(self):
        for widget in self._widgets.values():
            if widget:
                widget.show()

    def set_buffer(self, buf):
        self._buffer = buf

    def get_buffer(self):
        return self._buffer

    def copy(self):
        anchor = RichTextAnchor()
        anchor.set_buffer(self._buffer)
        return anchor

    def highlight(self):
        for widget in self._widgets.values():
            if widget:
                widget.highlight()

    def unhighlight(self):
        for widget in self._widgets.values():
            if widget:
                widget.unhighlight()

class RichTextBaseBuffer(Gtk.TextBuffer):
    """Basic RichTextBuffer with the following features

        - maintains undo/redo stacks
    """
    __gsignals__ = {
        "ending-user-action": (GObject.SIGNAL_RUN_LAST, None, ()),
    }

    def __init__(self, tag_table=RichTextBaseTagTable()):
        super().__init__(tag_table=tag_table)
        tag_table.add_textbuffer(self)

        # Undo handler
        self._undo_handler = UndoHandler(self)
        self._undo_handler.after_changed.add(self.on_after_changed)
        self.undo_stack = self._undo_handler.undo_stack

        # Insert mark tracking
        self._insert_mark = self.get_insert()
        self._old_insert_mark = self.create_mark(
            None, self.get_iter_at_mark(self._insert_mark), True)

        self._user_action_ending = False
        self._noninteractive = 0

        # Setup signals
        self._signals = [
            # Local events
            self.connect("begin_user_action", self._on_begin_user_action),
            self.connect("end_user_action", self._on_end_user_action),
            self.connect("mark-set", self._on_mark_set),
            self.connect("insert-text", self._on_insert_text),
            self.connect("insert-child-anchor", self._on_insert_child_anchor),
            self.connect("apply-tag", self._on_apply_tag),
            self.connect("remove-tag", self._on_remove_tag),
            self.connect("delete-range", self._on_delete_range),

            # Undo handler events
            self.connect("insert-text", self._undo_handler.on_insert_text),
            self.connect("delete-range", self._undo_handler.on_delete_range),
            self.connect("insert-pixbuf", self._undo_handler.on_insert_pixbuf),
            self.connect("insert-child-anchor",
                         self._undo_handler.on_insert_child_anchor),
            self.connect("apply-tag", self._undo_handler.on_apply_tag),
            self.connect("remove-tag", self._undo_handler.on_remove_tag),
            self.connect("changed", self._undo_handler.on_changed)
        ]

    def block_signals(self):
        """Block all signal handlers"""
        for signal in self._signals:
            self.handler_block(signal)
        self.undo_stack.suppress()

    def unblock_signals(self):
        """Unblock all signal handlers"""
        for signal in self._signals:
            self.handler_unblock(signal)
        self.undo_stack.resume()
        self.undo_stack.reset()

    def clear(self, clear_undo=False):
        """Clear buffer contents"""
        start = self.get_start_iter()
        end = self.get_end_iter()

        if clear_undo:
            self.undo_stack.suppress()

        self.begin_user_action()
        self.remove_all_tags(start, end)
        self.delete(start, end)
        self.end_user_action()

        if clear_undo:
            self.undo_stack.resume()
            self.undo_stack.reset()

    def get_insert_iter(self):
        """Return TextIter for insert point"""
        return self.get_iter_at_mark(self.get_insert())

    # Restrict cursor and insert
    def is_insert_allowed(self, it, text=""):
        """Check that insert is allowed at TextIter 'it'"""
        return it.can_insert(True)

    def is_cursor_allowed(self, it):
        """Returns True if cursor is allowed at TextIter 'it'"""
        return True

    # Child widgets
    def add_child(self, it, child):
        """Add TextChildAnchor to buffer"""
        pass

    def update_child(self, action):
        if isinstance(action, InsertChildAction):
            # Set buffer of child
            action.child.set_buffer(self)

    # Selection callbacks
    def on_selection_changed(self):
        pass

    # Paragraph change callbacks
    def on_paragraph_split(self, start, end):
        pass

    def on_paragraph_merge(self, start, end):
        pass

    def on_paragraph_change(self, start, end):
        pass

    def update_paragraphs(self, action):
        if isinstance(action, InsertAction):
            # Detect paragraph splitting
            if "\n" in action.text:
                par_start = self.get_iter_at_offset(action.pos)
                par_end = par_start.copy()
                par_start.backward_line()
                par_end.forward_chars(action.length)
                par_end.forward_line()
                self.on_paragraph_split(par_start, par_end)

        elif isinstance(action, DeleteAction):
            # Detect paragraph merging
            if "\n" in action.text:
                par_start, par_end = get_paragraph(
                    self.get_iter_at_offset(action.start_offset))
                self.on_paragraph_merge(par_start, par_end)

    # Tag apply/remove
    def remove_tag(self, tag, start, end):
        super().remove_tag(tag, start, end)

    # Callbacks
    def _on_mark_set(self, textbuffer, it, mark):
        """Callback for mark movement"""
        if mark is self._insert_mark:
            # If cursor is not allowed here, move it back
            old_insert = self.get_iter_at_mark(self._old_insert_mark)
            if not self.get_iter_at_mark(mark).equal(old_insert) and \
               not self.is_cursor_allowed(it):
                self.place_cursor(old_insert)
                return

            # When cursor moves, selection changes
            self.on_selection_changed()

            # Keep track of cursor position
            self.move_mark(self._old_insert_mark, it)

    def _on_insert_text(self, textbuffer, it, text, length):
        """Callback for text insert"""
        # In GTK 3, text is already a UTF-8 string, no need for conversion
        # Check to see if insert is allowed
        if textbuffer.is_interactive() and \
           not self.is_insert_allowed(it, text):
            textbuffer.stop_emission("insert-text")

    def _on_insert_child_anchor(self, textbuffer, it, anchor):
        """Callback for inserting a child anchor"""
        if not self.is_insert_allowed(it, ""):
            self.stop_emission("insert-child-anchor")

    def _on_apply_tag(self, textbuffer, tag, start, end):
        """Callback for tag apply"""
        if not isinstance(tag, RichTextTag):
            # Do not process tags that are not rich text
            # i.e. gtkspell tags (ignored by undo/redo)
            return

        if tag.is_par_related():
            self.on_paragraph_change(start, end)

    def _on_remove_tag(self, textbuffer, tag, start, end):
        """Callback for tag remove"""
        if not isinstance(tag, RichTextTag):
            # Do not process tags that are not rich text
            # i.e. gtkspell tags (ignored by undo/redo)
            return

        if tag.is_par_related():
            self.on_paragraph_change(start, end)

    def _on_delete_range(self, textbuffer, start, end):
        pass

    def on_after_changed(self, action):
        """
        Callback after content change has occurred

        Fix up textbuffer to restore consistent state (paragraph tags,
        current font application)
        """
        self.begin_user_action()

        self.update_current_tags(action)
        self.update_paragraphs(action)
        self.update_child(action)

        self.end_user_action()

    # Records whether text insert is currently user interactive, or is automated
    def begin_noninteractive(self):
        """Begins a noninteractive mode"""
        self._noninteractive += 1

    def end_noninteractive(self):
        """Ends a noninteractive mode"""
        self._noninteractive -= 1

    def is_interactive(self):
        """Returns True when insert is currently interactive"""
        return self._noninteractive == 0

    # Undo/redo methods
    def undo(self):
        """Undo the last action in the RichTextView"""
        self.begin_noninteractive()
        self.undo_stack.undo()
        self.end_noninteractive()

    def redo(self):
        """Redo the last action in the RichTextView"""
        self.begin_noninteractive()
        self.undo_stack.redo()
        self.end_noninteractive()

    def _on_begin_user_action(self, textbuffer):
        """Begin a composite undo/redo action"""
        self.undo_stack.begin_action()

    def _on_end_user_action(self, textbuffer):
        """End a composite undo/redo action"""
        if not self.undo_stack.is_in_progress() and \
           not self._user_action_ending:
            self._user_action_ending = True
            self.emit("ending-user-action")
            self._user_action_ending = False
        self.undo_stack.end_action()