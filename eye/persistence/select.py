import sys
from pathlib import Path

from eye.persistence.adapters.filesystem import FilesystemSaveStore
from eye.persistence.adapters.local_storage import LocalStorageSaveStore
from eye.persistence.port import SaveStore


def default_save_store(namespace: str, filesystem_path: Path | None = None) -> SaveStore:
    if sys.platform == "emscripten":
        import platform

        return LocalStorageSaveStore(platform.window.localStorage, key=f"eye-of-the-swarm-{namespace}")
    if filesystem_path is None:
        raise ValueError("filesystem_path is required outside emscripten")
    return FilesystemSaveStore(filesystem_path)
