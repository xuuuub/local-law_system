"""修复 PATH 中带引号的 Java 条目"""
import winreg

BAD = '"D:\\java\\bin;D:\\java\\jre\\bin;"'
GOOD = 'D:\\java\\bin;D:\\java\\jre\\bin'

for root, name in [
    (winreg.HKEY_CURRENT_USER, "用户PATH"),
    (winreg.HKEY_LOCAL_MACHINE, "系统PATH"),
]:
    try:
        key = winreg.OpenKey(
            root,
            r"Environment" if root == winreg.HKEY_CURRENT_USER
            else r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        )
        path, regtype = winreg.QueryValueEx(key, "PATH")
        if BAD in path:
            new_path = path.replace(BAD, GOOD)
            winreg.SetValueEx(key, "PATH", 0, regtype, new_path)
            print(f"{name}: 已修复")
        else:
            print(f"{name}: 无问题")
        winreg.CloseKey(key)
    except Exception as e:
        print(f"{name}: {e}")

import ctypes
ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, None, 0, 5000, None)
print("完成，重启 PowerShell 生效")
