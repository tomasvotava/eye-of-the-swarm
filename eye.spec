# PyInstaller spec for the native GUI build; run through `make exe`.
import sys

from PyInstaller.utils.hooks import collect_data_files

# `eye` isn't installed into the venv, so the hook subprocess can only import it from the repo root.
sys.path.insert(0, SPECPATH)

a = Analysis(
    ["eye/main.py"],
    datas=collect_data_files("eye"),
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="eye-of-the-swarm",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="eye-of-the-swarm")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="The Eye of the Swarm.app", bundle_identifier="eu.tomasvotava.eye-of-the-swarm")
