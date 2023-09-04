import operator
from abc import abstractmethod
from enum import Enum, auto
from pathlib import Path
from typing import Collection, Generic, List, Tuple, TypeVar

from django.core.files.storage import FileSystemStorage as BaseFileSystemStorage, Storage


class SortKey(Enum):
    NAME = auto()
    SIZE = auto()
    ISDIR = auto()
    CTIME = auto()
    MTIME = auto()


SortKeyWithOrder = Tuple[SortKey, bool]
SortKeyArg = Collection[SortKey | SortKeyWithOrder]
_T = TypeVar("_T", bound=object)


def normalize_sort_keys(keys: SortKeyArg) -> List[SortKeyWithOrder]:
    ret = []
    for key in keys:
        if isinstance(key, SortKey):
            ret.append((key, False))
        else:
            ret.append(key)
    return ret


class SortableStorage(Storage, Generic[_T]):
    def sort_by(self, files: Collection[_T], keys: SortKeyArg) -> List[_T]:
        nkeys = normalize_sort_keys(keys)
        reverse_all = False

        for (key, reverse) in nkeys:
            if key == SortKey.NAME:
                reverse_all = reverse

        return sorted(files, key=lambda f: self.get_sort_value(f, nkeys, reverse), reverse=reverse_all)

    @abstractmethod
    def get_sort_value(
        self,
        file: _T,
        nkeys: List[SortKeyWithOrder],
        reverse_all: bool
    ) -> List[str | int | float]:
        raise NotImplementedError("SortableStorage subclasses must implement get_sort_value().")

    @abstractmethod
    def list_recursive(self, path: str = "", sort: SortKeyArg | None = None) -> List[str]:
        """Recursively lists files in `path`, ordered by `sort`."""
        raise NotImplementedError("SortableStorage subclasses must implement list_recursive().")


class FileSystemStorage(SortableStorage[Path], BaseFileSystemStorage):
    def get_sort_value(self, file, nkeys, reverse_all):
        stat = file.stat()
        result: List[str | int | float] = []
        for (key, reverse) in nkeys:
            reverse = operator.xor(reverse, reverse_all)
            multiplier = -1 if reverse else 1
            if key == SortKey.NAME:
                result.append(file.name)
            elif key == SortKey.ISDIR:
                result.append(operator.xor(file.is_dir(), reverse))
            elif key == SortKey.SIZE:
                if file.is_dir():
                    result.append(0)
                else:
                    result.append(stat.st_size * multiplier)
            elif key == SortKey.CTIME:
                result.append(stat.st_ctime * multiplier)
            elif key == SortKey.MTIME:
                result.append(stat.st_mtime * multiplier)
        return result

    def recurse(self, path: Path | str, sort: SortKeyArg | None = None) -> List[Path]:
        """
        Recursively gets Path objects for files in `path`, ordered by `sort`.
        """
        files = []
        if isinstance(path, str):
            path = Path(path)
        for entry in path.iterdir():
            if entry.is_dir():
                files.extend(self.recurse(entry))
            else:
                files.append(entry)
        return self.sort_by(files, sort or [])

    def list_recursive(self, path="", sort=None):
        full_path = self.path(path)
        return [str(p)[len(full_path):].strip("/") for p in self.recurse(full_path, sort or [])]
