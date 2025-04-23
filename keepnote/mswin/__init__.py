import os

import sys
# 仅在 Windows 下导入 winreg
if sys.platform.startswith("win"):
    import winreg


def get_my_documents():
    """Returns path to My Documents folder on Windows, or ~/Documents on others"""
    if sys.platform.startswith("win"):
        try:
            # 打开注册表键
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders"
            )
            # 读取 "Personal" 值（对应 "My Documents" 或 "Documents" 路径）
            path, _ = winreg.QueryValueEx(key, "Personal")
            winreg.CloseKey(key)
            if path and os.path.exists(path):
                return path
        except (OSError, FileNotFoundError, WindowsError):
            # 如果注册表读取失败，回退到其他方法
            pass

        # 回退到使用环境变量 USERPROFILE
        user_profile = os.getenv("USERPROFILE")
        if user_profile:
            default_path = os.path.join(user_profile, "Documents")
            if os.path.exists(default_path):
                return default_path

    # 非 Windows 系统或上面失败时，使用 ~/Documents
    default_path = os.path.join(os.path.expanduser("~"), "Documents")
    if os.path.exists(default_path):
        return default_path

    return None