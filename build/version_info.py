# PyInstaller Win32 VSVersionInfo for scan2bim.
# Loaded by EXE(version='build/version_info.py', ...).
# Keep in sync with src/scan2bim/_version.py — bump both when releasing.

VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(0, 9, 6, 0),
        prodvers=(0, 9, 6, 0),
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "Lauri Rekola"),
                        StringStruct("FileDescription", "scan2bim — point cloud to IFC/DXF"),
                        StringStruct("FileVersion", "0.9.6"),
                        StringStruct("InternalName", "scan2bim"),
                        StringStruct("LegalCopyright", "(c) 2026 Lauri Rekola"),
                        StringStruct("OriginalFilename", "scan2bim.exe"),
                        StringStruct("ProductName", "scan2bim"),
                        StringStruct("ProductVersion", "0.9.6"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)
