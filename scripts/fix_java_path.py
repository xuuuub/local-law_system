"""
修复系统 PATH 中 D:\java 条目被引号包裹的问题（需管理员）
"""
import winreg

KEY_PATH = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

key = winreg.OpenKey(
    winreg.HKEY_LOCAL_MACHINE, KEY_PATH,
    0, winreg.KEY_READ | winreg.KEY_WRITE
)
path, regtype = winreg.QueryValueEx(key, "PATH")

BAD = '"D:\\java\\bin;D:\\java\\jre\\bin;"'
GOOD = 'D:\\java\\bin;D:\\java\\jre\\bin;'

if BAD not in path:
    print("未找到错误条目，可能已修复")
    winreg.CloseKey(key)
    exit()

path = path.replace(BAD, GOOD)
print(f"旧: ...{BAD}...")
print(f"新: ...{GOOD}...")

# 恢复为 REG_EXPAND_SZ（之前被改成了 REG_SZ）
winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, path)
winreg.CloseKey(key)
print("已修复，重启 PowerShell 生效")
