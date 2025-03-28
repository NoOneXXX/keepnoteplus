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
    mode     -- write mode (default: 'r')
    tmp      -- specify tempfile
    codec    -- preferred encoding
    """
    stream = SafeFile(filename, mode, tmp)

    if "b" not in mode and codec:
        if "r" in mode:
            stream = codecs.getreader(codec)(stream)
        elif "w" in mode:
            stream = codecs.getwriter(codec)(stream)

    return stream

class SafeFile:
    def __init__(self, filename, mode="r", tmp=None):
        # Set tempfile
        if "w" in mode and tmp is None:
            f, tmp = tempfile.mkstemp(".tmp", filename + "_", dir=".")
            os.close(f)

        self._tmp = tmp
        self._filename = filename
        self._mode = mode

        # 打开文件时明确指定文本模式和编码
        self.file = builtins.open(filename, mode, buffering=1, encoding="utf-8" if "b" not in mode else None)

    def write(self, data):
        """Write data to the file"""
        if isinstance(data, bytes):
            raise TypeError("SafeFile.write() expects str, not bytes")
        self.file.write(data)

    def read(self, size=-1):
        """Read data from the file"""
        return self.file.read(size)

    def close(self):
        """Closes file and moves temp file to final location"""
        try:
            self.file.flush()
            os.fsync(self.file.fileno())
        except Exception:
            pass

        self.file.close()

        if self._tmp:
            # NOTE: Windows does not allow renaming when the destination file exists
            if sys.platform.startswith("win") and os.path.exists(self._filename):
                os.remove(self._filename)
            os.rename(self._tmp, self._filename)
            self._tmp = None

    def discard(self):
        """
        Close and discard written data.
        Temp file does not replace existing file
        """
        self.file.close()

        if self._tmp:
            os.remove(self._tmp)
            self._tmp = None

    def get_tempfile(self):
        """Returns tempfile filename"""
        return self._tmp

    def __enter__(self):
        """Support for context manager"""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Ensure file is properly closed"""
        self.close()