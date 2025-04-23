"""
KeepNote
Safely write to a tempfile before replacing previous file.
"""

import codecs
import os
import sys
import tempfile
import builtins

def open(filename, mode="r", tmp=None, codec=None):
    """
    Opens a file that writes to a temp location and replaces existing file
    on close.

    filename -- filename to open
    mode     -- file mode (e.g., 'r', 'w', 'rb', 'wb')
    tmp      -- specify tempfile (optional)
    codec    -- preferred encoding (ignored in binary mode)
    """
    stream = SafeFile(filename, mode, tmp, codec=codec)
    return stream

class SafeFile:
    def __init__(self, filename, mode="r", tmp=None, codec=None):
        # Set tempfile for writing
        if "w" in mode and tmp is None:
            f, tmp = tempfile.mkstemp(".tmp", os.path.basename(filename) + "_",
                                    dir=os.path.dirname(filename) or ".")
            os.close(f)

        self._tmp = tmp
        self._filename = filename
        self._mode = mode
        self._codec = codec

        # Check if binary mode
        is_binary = "b" in mode

        # Open file with appropriate parameters
        if is_binary:
            self.file = builtins.open(
                self._tmp if self._tmp else filename,
                mode,
                buffering=0  # No buffering for binary mode
            )
        else:
            self.file = builtins.open(
                self._tmp if self._tmp else filename,
                mode,
                buffering=1,  # Line buffering for text mode
                encoding=codec if codec else "utf-8"
            )

    def write(self, data):
        """Write data to the file"""
        if "b" in self._mode:
            if not isinstance(data, bytes):
                raise TypeError("SafeFile.write() expects bytes in binary mode")
        else:
            if not isinstance(data, str):
                raise TypeError("SafeFile.write() expects str in text mode")
        self.file.write(data)

    def read(self, size=-1):
        """Read data from the file"""
        return self.file.read(size)

    def close(self):
        """Closes file and moves temp file to final location"""
        try:
            self.file.flush()
            if hasattr(self.file, 'fileno'):
                os.fsync(self.file.fileno())
        except Exception:
            pass

        self.file.close()

        if self._tmp and "w" in self._mode:
            if sys.platform.startswith("win") and os.path.exists(self._filename):
                os.remove(self._filename)
            os.rename(self._tmp, self._filename)
            self._tmp = None

    def discard(self):
        """Close and discard written data"""
        self.file.close()
        if self._tmp:
            os.remove(self._tmp)
            self._tmp = None

    def get_tempfile(self):
        """Returns tempfile filename"""
        return self._tmp

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

safe_open = open