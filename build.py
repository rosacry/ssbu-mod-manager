"""Build script for SSBU Mod Manager - creates standalone .exe"""
import PyInstaller.__main__
import os

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Get absolute path to icon
icon_path = os.path.abspath('assets/icon.ico')

args = [
    'main.py',
    '--name=SSBUModManager',
    '--onefile',
    '--windowed',
    '--add-data=ParamLabels.csv;.',
    '--hidden-import=pyprc',
    '--hidden-import=LMS',
    '--hidden-import=LMS.Message',
    '--hidden-import=LMS.Message.MSBT',
    '--hidden-import=LMS.Stream',
    '--hidden-import=LMS.Stream.Reader',
    '--hidden-import=LMS.Stream.Writer',
    '--collect-all=LMS',
    '--hidden-import=customtkinter',
    '--collect-all=customtkinter',
    '--hidden-import=PIL',
    '--hidden-import=PIL._tkinter_finder',
    '--hidden-import=pygame',
    '--add-data=assets;assets',
    '--noconfirm',
    '--clean',
]

# Add icon - use absolute path
if os.path.exists(icon_path):
    args.append(f'--icon={icon_path}')
    print(f"Using icon: {icon_path}")
else:
    print("WARNING: Icon file not found at assets/icon.ico")

print("Building SSBU Mod Manager...")
PyInstaller.__main__.run(args)
print("\nBuild complete! Check the 'dist' folder for SSBUModManager.exe")
