# keepnote.py/utils/platform.py
import sys
import os

import keepnote.trans
# 获取模块路径（对应 keepnote.py 包所在目录）
BASEDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def get_platform():
    if sys.platform == "darwin":
        return "darwin"
    elif sys.platform.startswith("win"):
        return "windows"
    elif sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def get_resource(*path_list):
    return os.path.join(BASEDIR, *path_list)

def unicode_gtk(text):
    if text is None:
        return None
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return text  # Already a string in Python 3

# keepnote.py/util/perform.py



def translate(message):
    """Translate a message using keepnote.py.trans.translate."""
    return keepnote.trans.translate(message)


def compose(*funcs):
    """
    Compose multiple functions from right to left.

    Example:
        compose(str, int)(x) == str(int(x))

    Args:
        *funcs: Variable number of functions to compose.

    Returns:
        A function that applies the given functions in sequence (right-to-left).
    """

    def fn(x):
        result = x
        for f in reversed(funcs):
            result = f(result)
        return result

    return fn