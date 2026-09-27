# PyInstaller Win32 VSVersionInfo for ordinate.
# Loaded by EXE(version='build/version_info.py', ...).
# Keep in sync with src/ordinate/_version.py — bump both when releasing.

VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(0, 9, 35, 0),
        prodvers=(0, 9, 35, 0),
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
                        StringStruct("FileDescription", "Ordinate — point cloud to IFC/DXF"),
                        StringStruct("FileVersion", "0.9.35"),
                        StringStruct("InternalName", "Ordinate"),
                        StringStruct("LegalCopyright", "(c) 2026 Lauri Rekola"),
                        StringStruct("OriginalFilename", "Ordinate.exe"),
                        StringStruct("ProductName", "Ordinate"),
                        StringStruct("ProductVersion", "0.9.35"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)
