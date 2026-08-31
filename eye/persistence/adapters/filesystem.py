import os
import tempfile
from pathlib import Path


class FilesystemSaveStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> str | None:
        try:
            return self._path.read_text()
        except FileNotFoundError:
            return None

    def save(self, data: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w") as tmp_file:
                tmp_file.write(data)
            tmp_path.replace(self._path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
