"""
MS Windows utilities for KeepNote
"""
# 移除对 screenshot 的导入
# from .screenshot import take_screenshot

try:
    import pywintypes
    import winerror
    from win32com.shell import shell, shellcon
    import win32api
    import win32gui
    import win32con
    import win32ui

    import ctypes.windll.kernel32

    # pyflakes ignore
    pywintypes
    winerror
    shell
    shellcon
    win32api
    win32gui
    win32con
    win32ui
    ctypes

except:
    pass

def get_my_documents():
    """Return the My Documents folder"""
    # See:
    # http://msdn.microsoft.com/en-us/library/windows/desktop/bb776887%28v=vs.85%29.aspx#mydocs  # nopep8
    # http://msdn.microsoft.com/en-us/library/bb762494%28v=vs.85%29.aspx#csidl_personal  # nopep8

    try:
        df = shell.SHGetDesktopFolder()
        pidl = df.ParseDisplayName(
            0, None, "::{450d8fba-ad25-11d0-98a8-0800361b1103}")[1]
    except pywintypes.com_error as e:
        if e.hresult == winerror.E_INVALIDARG:
            # This error occurs when the My Documents virtual folder
            # is not available below the Desktop virtual folder in the
            # file system.  This may be the case if it has been made
            # unavailable using a Group Policy setting.  See
            # http://technet.microsoft.com/en-us/library/cc978354.aspx.
            pidl = shell.SHGetSpecialFolderLocation(0, shellcon.CSIDL_PERSONAL)
        else:
            raise
    mydocs = shell.SHGetPathFromIDList(pidl)

    # TODO: may need to handle window-specific encoding here.
    #encoding = locale.getdefaultlocale()[1]
    #if encoding is None:
    #    encoding = "utf-8"

    return mydocs