# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — scan2bim GUI .exe (Windows, onedir)

Aja:  pyinstaller scan2bim.spec
Tulos: dist/scan2bim/scan2bim.exe
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# ifcopenshell toimittaa omat shared-libraryt — kerätään ne mukaan
import ifcopenshell, open3d
IFOCOS_PATH = Path(ifcopenshell.__file__).parent
O3D_PATH    = Path(open3d.__file__).parent

# onnxruntime (kalustesuodatin) — kerää data + dynaamiset kirjastot
_ort_datas = collect_data_files("onnxruntime")
_ort_bins  = collect_dynamic_libs("onnxruntime")

# PointNet ONNX-malli — bundlaa exe:hen jos löytyy (models/s3dis_pointnet.onnx)
_model_file  = os.path.join(SPECPATH, "models", "s3dis_pointnet.onnx")
_model_datas = [(_model_file, "models")] if os.path.exists(_model_file) else []

# Lisätään ifcopenshell-kansio kokonaan (sisältää api/, express/, util/ jne.)
ifc_datas = []
for root, dirs, files in os.walk(str(IFOCOS_PATH)):
    # Jätä pois __pycache__ ja .pyc-kansiot
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    rel = os.path.relpath(root, str(IFOCOS_PATH.parent))
    for f in files:
        if not f.endswith(".pyc"):
            ifc_datas.append((os.path.join(root, f), rel))

a = Analysis(
    ["src/scan2bim/gui/__main__.py"],
    pathex=["src"],
    binaries=_ort_bins,
    datas=ifc_datas + _ort_datas + _model_datas,
    hiddenimports=[
        # onnxruntime (kalustesuodatin)
        "onnxruntime",
        "onnxruntime.capi",
        "onnxruntime.capi._pybind_state",
        # pye57 C-laajennus
        "pye57",
        # laspy
        "laspy",
        "lazrs",
        # open3d
        "open3d",
        "open3d.cpu.pybind",
        # scipy
        "scipy.spatial",
        "scipy.spatial._qhull",
        "scipy.spatial.transform._rotation_groups",
        # ezdxf
        "ezdxf",
        "ezdxf.lldxf",
        # ifcopenshell
        "ifcopenshell",
        "ifcopenshell.api",
        "ifcopenshell.guid",
        # pydantic
        "pydantic",
        "pydantic.v1",
        # PySide6
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scan2bim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # UPX voi rikkoa PySide6-binaarit
    console=False,    # ei komentorivi-ikkunaa (GUI-sovellus)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,        # TODO: lisää icon.ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="scan2bim",
)
