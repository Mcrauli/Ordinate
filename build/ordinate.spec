# PyInstaller .spec for ordinate â€” onefile windowed Windows build.
# Build:  .venv\Scripts\python -m PyInstaller build/ordinate.spec --clean --noconfirm
# Output: dist/ordinate.exe
#
# ordinate bundles heavy native deps (open3d, scipy, opencv, ifcopenshell)
# whose submodules / data files / dynamic libs PyInstaller cannot see
# statically â€” collect them explicitly below.

import os
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    collect_dynamic_libs,
)

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

# â”€â”€ Submodules imported lazily at runtime â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# scipy/open3d core modules are covered by PyInstaller's standard hooks â€”
# do NOT collect_submodules them or the bundle balloons with their
# tests/ and examples/ trees (and open3d.examples even tries torch/tf).
_ifc_api = collect_submodules('ifcopenshell.api')
_ifc_express = collect_submodules('ifcopenshell.express')
_ezdxf = collect_submodules('ezdxf')

# 3D-tarkastusnÃ¤kymÃ¤ (gui/inspect_view.py): pyqtgraph.opengl + PyOpenGL.
# OpenGL.arrays.* ja OpenGL.platform.* ladataan dynaamisesti (ctypes) â†’
# staattinen analyysi ei nÃ¤e niitÃ¤, collect_submodules pakko.
_pyqtgraph = collect_submodules('pyqtgraph')
_pyopengl = collect_submodules('OpenGL')

# â”€â”€ Data files (JSON schemas, native resources) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_ifc_data = collect_data_files('ifcopenshell')
_open3d_data = collect_data_files('open3d')
_laspy_data = collect_data_files('laspy')
_pyqtgraph_data = collect_data_files('pyqtgraph')

# â”€â”€ Dynamic libs (open3d / pye57 ship .dll/.pyd not seen statically) â”€â”€â”€
_open3d_bins = collect_dynamic_libs('open3d')
_pye57_bins = collect_dynamic_libs('pye57')

# â”€â”€ onnxruntime (kalustesuodatin) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_ort_data = collect_data_files('onnxruntime')
_ort_bins = collect_dynamic_libs('onnxruntime')

# â”€â”€ PointNet ONNX-malli (bundlataan exe:hen jos lÃ¶ytyy) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Vain YKSI mallitiedosto: retail-variantti on alias samalle mallille
# (cb50610 sulautti ne). Molempien bundlaaminen lisÃ¤si 3.4 MB turhaa
# jokaiseen latauksen ja itsepÃ¤ivitykseen; PointNetFilter putoaa
# oletusmalliin kun retail-tiedostoa ei ole.
# Puuttuva malli EI saa mennÃ¤ hiljaa lÃ¤pi: exe rakentuisi normaalisti ja
# putki putoaisi geometriseen fallbackiin, eli asiakas saisi mitatusti
# huonomman tuloksen ilman ettÃ¤ kukaan huomaa buildissa mitÃ¤Ã¤n. Sama
# tuotesÃ¤Ã¤ntÃ¶ kuin muuallakin: hiljainen heikennys on pahempi kuin virhe.
_model_file = os.path.join(ROOT, 'models', 's3dis_pointnet.onnx')
if not os.path.exists(_model_file):
    raise SystemExit(
        "BUILD KESKEYTETTY: semanttisen suodattimen malli puuttuu:\n"
        + _model_file + "\n"
        "Ilman sita exe kaantyy mutta putki ajaa geometrisella fallbackilla.\n"
        "Hae malli gitista: git checkout -- models/s3dis_pointnet.onnx")
_model_data = [(_model_file, 'models'), (os.path.join(ROOT, 'models', 'wall_verifier.json'), 'models')]

# Kolmannen osapuolen lisenssit on TOIMITETTAVA sovelluksen mukana: MIT
# (Cloud2BIM, ks. wall_contour.py) vaatii copyright-ilmoituksen sÃ¤ilyttÃ¤misen ja
# LGPL (IfcOpenShell, Qt) lisenssitekstin. Ks. THIRD-PARTY-NOTICES.md.
_notice_file = os.path.join(ROOT, 'THIRD-PARTY-NOTICES.md')
_notice_data = [(_notice_file, '.')] if os.path.exists(_notice_file) else []

block_cipher = None

_icon_path = os.path.join(ROOT, 'assets', 'ordinate.ico')
_icon = _icon_path if os.path.exists(_icon_path) else None

a = Analysis(
    [os.path.join(ROOT, 'src/ordinate/gui/__main__.py')],
    pathex=[os.path.join(ROOT, 'src')],
    binaries=_open3d_bins + _pye57_bins + _ort_bins,
    datas=_ifc_data + _open3d_data + _laspy_data + _ort_data + _model_data + _notice_data + _pyqtgraph_data,
    hiddenimports=[
        'ordinate',
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
        'pyqtgraph',
        'pyqtgraph.opengl',
        'OpenGL',
        'OpenGL.GL',
        'OpenGL.platform.win32',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
    ] + _ifc_api + _ifc_express + _ezdxf + _pyqtgraph + _pyopengl,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy.distutils',
        'setuptools._distutils',
        'pip',
        # Bloat we never import â€” open3d viewer/ML stack, dev tooling.
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

# KOMENTORIVI OMANA EXENAAN. GUI-exe on `console=False`, joten silla ei ole
# stdoutia eika komentorivi toimi siina lainkaan â€” `ordinate.exe convert ...`
# vain avaa ikkunan. Eraajo, skriptaus ja asiakkaan oma automaatio tarvitsevat
# konsoliversion, ja se on saatava SAMASTA paketista: kaiken on tultava exesta.
# Sama Analysis â†’ tasmalleen samat riippuvuudet ja sama malli, ei toista
# latausta eika versioeroa.
a_cli = Analysis(
    [os.path.join(ROOT, 'src/ordinate/cli.py')],
    pathex=[os.path.join(ROOT, 'src')],
    binaries=[],
    datas=[],
    hiddenimports=a.hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)

# ONE-DIR, ei one-file. Syy on juridinen: IfcOpenShell ja Qt (PySide6) ovat
# LGPL-3.0, ja LGPL Â§4(d)(1) edellyttÃ¤Ã¤ ettÃ¤ kÃ¤yttÃ¤jÃ¤ voi VAIHTAA kirjaston
# omaan versioonsa. One-file purkaa kaiken vÃ¤liaikaishakemistoon â†’ ei tÃ¤yty.
# One-dirissÃ¤ .dll/.pyd ovat omina tiedostoinaan asennushakemistossa â†’ tÃ¤yttyy.
# IfcOpenShellille ei ole kaupallista lisenssiÃ¤, joten tÃ¤tÃ¤ ei voi ostaa pois.
# ItsepÃ¤ivitys toimii silti hiljaisena: ks. updater.replace_app_dir.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Ordinate',
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

exe_legacy = EXE(
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

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name='ordinate-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    exe_legacy,
    exe_cli,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ordinate',
)
