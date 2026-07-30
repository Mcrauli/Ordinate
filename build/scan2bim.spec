# PyInstaller .spec for scan2bim — onefile windowed Windows build.
# Build:  .venv\Scripts\python -m PyInstaller build/scan2bim.spec --clean --noconfirm
# Output: dist/scan2bim.exe
#
# scan2bim bundles heavy native deps (open3d, scipy, opencv, ifcopenshell)
# whose submodules / data files / dynamic libs PyInstaller cannot see
# statically — collect them explicitly below.

import os
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    collect_dynamic_libs,
)

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

# ── Submodules imported lazily at runtime ──────────────────────────────
# scipy/open3d core modules are covered by PyInstaller's standard hooks —
# do NOT collect_submodules them or the bundle balloons with their
# tests/ and examples/ trees (and open3d.examples even tries torch/tf).
_ifc_api = collect_submodules('ifcopenshell.api')
_ifc_express = collect_submodules('ifcopenshell.express')
_ezdxf = collect_submodules('ezdxf')

# ── Data files (JSON schemas, native resources) ────────────────────────
_ifc_data = collect_data_files('ifcopenshell')
_open3d_data = collect_data_files('open3d')
_laspy_data = collect_data_files('laspy')

# ── Dynamic libs (open3d / pye57 ship .dll/.pyd not seen statically) ───
_open3d_bins = collect_dynamic_libs('open3d')
_pye57_bins = collect_dynamic_libs('pye57')

# ── onnxruntime (kalustesuodatin) ──────────────────────────────────────────
_ort_data = collect_data_files('onnxruntime')
_ort_bins = collect_dynamic_libs('onnxruntime')

# ── PointNet ONNX-malli (bundlataan exe:hen jos löytyy) ───────────────────
# Vain YKSI mallitiedosto: retail-variantti on alias samalle mallille
# (cb50610 sulautti ne). Molempien bundlaaminen lisäsi 3.4 MB turhaa
# jokaiseen latauksen ja itsepäivitykseen; PointNetFilter putoaa
# oletusmalliin kun retail-tiedostoa ei ole.
_model_data = []
_model_file = os.path.join(ROOT, 'models', 's3dis_pointnet.onnx')
if os.path.exists(_model_file):
    _model_data.append((_model_file, 'models'))

# Kolmannen osapuolen lisenssit on TOIMITETTAVA sovelluksen mukana: MIT
# (Cloud2BIM, ks. wall_contour.py) vaatii copyright-ilmoituksen säilyttämisen ja
# LGPL (IfcOpenShell, Qt) lisenssitekstin. Ks. THIRD-PARTY-NOTICES.md.
_notice_file = os.path.join(ROOT, 'THIRD-PARTY-NOTICES.md')
_notice_data = [(_notice_file, '.')] if os.path.exists(_notice_file) else []

block_cipher = None

_icon_path = os.path.join(ROOT, 'assets', 'scan2bim.ico')
_icon = _icon_path if os.path.exists(_icon_path) else None

a = Analysis(
    [os.path.join(ROOT, 'src/scan2bim/gui/__main__.py')],
    pathex=[os.path.join(ROOT, 'src')],
    binaries=_open3d_bins + _pye57_bins + _ort_bins,
    datas=_ifc_data + _open3d_data + _laspy_data + _ort_data + _model_data + _notice_data,
    hiddenimports=[
        'scan2bim',
        'open3d',
        'scipy',
        'scipy.spatial',
        'scipy.spatial.transform',
        'cv2',
        'laspy',
        'lazrs',
        'pye57',
        'ifcopenshell',
        'ifcopenshell.api',
        'ifcopenshell.geom',
        'ifcopenshell.guid',
        'ifcopenshell.template',
        'ezdxf',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'onnxruntime',
        'onnxruntime.capi',
    ] + _ifc_api + _ifc_express + _ezdxf,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy.distutils',
        'setuptools._distutils',
        'pip',
        # Bloat we never import — open3d viewer/ML stack, dev tooling.
        'torch',
        'tensorflow',
        'open3d.examples',
        'open3d.ml',
        'IPython',
        'jedi',
        'pytest',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ONE-DIR, ei one-file. Syy on juridinen: IfcOpenShell ja Qt (PySide6) ovat
# LGPL-3.0, ja LGPL §4(d)(1) edellyttää että käyttäjä voi VAIHTAA kirjaston
# omaan versioonsa. One-file purkaa kaiken väliaikaishakemistoon → ei täyty.
# One-dirissä .dll/.pyd ovat omina tiedostoinaan asennushakemistossa → täyttyy.
# IfcOpenShellille ei ole kaupallista lisenssiä, joten tätä ei voi ostaa pois.
# Itsepäivitys toimii silti hiljaisena: ks. updater.replace_app_dir.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='scan2bim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=os.path.join(SPECPATH, 'version_info.py'),
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='scan2bim',
)
