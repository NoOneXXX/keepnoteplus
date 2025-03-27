"""
KeepNote
Screenshot utility for MS Windows

Copyright (c) 2008-2009 Matt Rasmussen
Author: Matt Rasmussen <rasmus@alum.mit.edu>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; version 2 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
"""

import sys

# win32api imports
try:
    import win32api
    import win32gui
    import win32con
    import win32ui
except ImportError as e:
    raise ImportError("pywin32 is required for screenshot functionality on Windows") from e

_g_class_num = 0

def capture_screen(filename: str, x: int, y: int, x2: int, y2: int) -> None:
    """Captures a screenshot from a region of the screen."""
    if x > x2:
        x, x2 = x2, x
    if y > y2:
        y, y2 = y2, y
    w, h = x2 - x, y2 - y

    screen_handle = win32gui.GetDC(0)
    screen_dc = win32ui.CreateDCFromHandle(screen_handle)
    shot_dc = screen_dc.CreateCompatibleDC()

    shot_bitmap = win32ui.CreateBitmap()
    shot_bitmap.CreateCompatibleBitmap(screen_dc, w, h)

    shot_dc.SelectObject(shot_bitmap)
    shot_dc.BitBlt((0, 0), (w, h), screen_dc, (x, y), win32con.SRCCOPY)

    shot_bitmap.SaveBitmapFile(shot_dc, filename)

    # Clean up resources
    shot_dc.DeleteDC()
    screen_dc.DeleteDC()
    win32gui.ReleaseDC(0, screen_handle)

class Window:
    """Class for basic MS Windows window."""
    def __init__(self, title: str = "Untitled",
                 style: int | None = None,
                 exstyle: int | None = None,
                 pos: tuple[int, int] = (0, 0),
                 size: tuple[int, int] = (400, 400),
                 background: int | None = None,
                 message_map: dict = None,
                 cursor: int | None = None):
        global _g_class_num

        if style is None:
            style = win32con.WS_OVERLAPPEDWINDOW
        if exstyle is None:
            exstyle = win32con.WS_EX_LEFT
        if background is None:
            background = win32con.COLOR_WINDOW
        if cursor is None:
            cursor = win32con.IDC_ARROW
        if message_map is None:
            message_map = {}

        self._instance = win32api.GetModuleHandle(None)

        self.message_map = {win32con.WM_DESTROY: self._on_destroy}
        self.message_map.update(message_map)

        _g_class_num += 1
        class_name = f"class_name{_g_class_num}"
        wc = win32gui.WNDCLASS()
        wc.hInstance = self._instance
        wc.lpfnWndProc = self.message_map
        wc.lpszClassName = class_name
        wc.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW
        wc.hbrBackground = background
        wc.cbWndExtra = 0
        wc.hCursor = win32gui.LoadCursor(0, cursor)
        wc.hIcon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

        class_atom = win32gui.RegisterClass(wc)

        self._handle = win32gui.CreateWindowEx(
            exstyle,
            class_name, title,
            style,
            pos[0], pos[1], size[0], size[1],
            0,  # no parent
            0,  # no menu
            self._instance,
            None
        )

    def show(self, enabled: bool = True) -> None:
        if enabled:
            win32gui.ShowWindow(self._handle, win32con.SW_SHOW)
        else:
            win32gui.ShowWindow(self._handle, win32con.SW_HIDE)

    def maximize(self) -> None:
        win32gui.ShowWindow(self._handle, win32con.SW_SHOWMAXIMIZED)

    def activate(self) -> None:
        win32gui.SetForegroundWindow(self._handle)

    def _on_destroy(self, hwnd: int, message: int, wparam: int, lparam: int) -> bool:
        self.close()
        return True

    def close(self) -> None:
        win32gui.DestroyWindow(self._handle)

class WinLoop:
    def __init__(self):
        self._running = True

    def start(self) -> None:
        while self._running:
            b, msg = win32gui.GetMessage(0, 0, 0)
            if not msg:
                break
            win32gui.TranslateMessage(msg)
            win32gui.DispatchMessage(msg)

    def stop(self) -> None:
        self._running = False

class ScreenShotWindow(Window):
    """ScreenShot Window."""
    def __init__(self, filename: str, shot_callback=None):
        x, y, w, h = win32gui.GetWindowRect(win32gui.GetDesktopWindow())

        super().__init__(
            "Screenshot", pos=(x, y), size=(w, h),
            style=win32con.WS_POPUP,
            exstyle=win32con.WS_EX_TRANSPARENT,
            background=0,
            message_map={
                win32con.WM_MOUSEMOVE: self._on_mouse_move,
                win32con.WM_LBUTTONDOWN: self._on_mouse_down,
                win32con.WM_LBUTTONUP: self._on_mouse_up
            },
            cursor=win32con.IDC_CROSS
        )

        self._filename = filename
        self._shot_callback = shot_callback
        self._drag = False
        self._draw = False

    def _on_mouse_down(self, hwnd: int, message: int, wparam: int, lparam: int) -> None:
        """Mouse down event."""
        self._drag = True
        self._start = win32api.GetCursorPos()

    def _on_mouse_up(self, hwnd: int, message: int, wparam: int, lparam: int) -> None:
        """Mouse up event."""
        if self._draw:
            self._drag = False
            self._draw = False

            hdc = win32gui.CreateDC("DISPLAY", None, None)
            pycdc = win32ui.CreateDCFromHandle(hdc)
            pycdc.SetROP2(win32con.R2_NOTXORPEN)

            win32gui.Rectangle(hdc, self._start[0], self._start[1],
                              self._end[0], self._end[1])

            capture_screen(self._filename, self._start[0], self._start[1],
                          self._end[0], self._end[1])

            pycdc.DeleteDC()
            win32gui.ReleaseDC(0, hdc)

        self.close()

        if self._shot_callback:
            self._shot_callback()

    def _on_mouse_move(self, hwnd: int, message: int, wparam: int, lparam: int) -> None:
        """Mouse moving event."""
        x, y = win32api.GetCursorPos()

        if self._drag:
            hdc = win32gui.CreateDC("DISPLAY", None, None)
            pycdc = win32ui.CreateDCFromHandle(hdc)
            pycdc.SetROP2(win32con.R2_NOTXORPEN)

            if self._draw:
                win32gui.Rectangle(hdc, self._start[0], self._start[1],
                                  self._end[0], self._end[1])

            self._draw = True
            win32gui.Rectangle(hdc, self._start[0], self._start[1], x, y)
            self._end = (x, y)

            pycdc.DeleteDC()
            win32gui.ReleaseDC(0, hdc)

def take_screenshot(filename: str) -> None:
    win32gui.InitCommonControls()

    def click():
        loop.stop()

    loop = WinLoop()
    win = ScreenShotWindow(filename, click)
    win.maximize()
    win.activate()
    loop.start()

def main(argv: list[str]) -> None:
    filename = argv[1] if len(argv) > 1 else "screenshot.bmp"
    take_screenshot(filename)

if __name__ == "__main__":
    main(sys.argv)