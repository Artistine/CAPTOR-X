# captioncast.spec
# Run with:  pyinstaller captioncast.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = [('fonts', 'fonts'), ('gui/index.html', 'gui'), ('gui/assets', 'gui/assets'), ('captor_core_icon.ico', '.')]
binaries = [('LibreHardwareMonitorLib.dll', '.')]
hiddenimports = [
    'tkinter',
    '_tkinter',
    'serial',
    'serial.tools',
    'serial.tools.list_ports',
    'numpy',
]

# collect all assets/binaries for libraries that PyInstaller struggles to bundle automatically
libs_to_collect = [
    'customtkinter', 
    'faster_whisper', 
    'ctranslate2', 
    'tokenizers', 
    'pyaudiowpatch', 
    'pyaudio', 
    'nvidia.cublas', 
    'nvidia.cudnn', 
    'nvidia.cuda_nvrtc',
    'wmi'
]

for pkg in libs_to_collect:
    try:
        d, b, h = collect_all(pkg)
        datas.extend(d)
        binaries.extend(b)
        hiddenimports.extend(h)
    except Exception as e:
        print(f"Warning collecting package {pkg}: {e}")

a = Analysis(
    ['captioncast_webview.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CaptorCore',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no black terminal window behind the app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='captor_core_icon.ico',
    version='file_version_info.txt',
    uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CaptorCoreBuild',
)


