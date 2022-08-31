import operator
from enum import Enum, auto
from pathlib import Path
from typing import Collection, Union

from django.core.files.storage import FileSystemStorage as BaseFileSystemStorage


class SortKey(Enum):
    NAME = auto()
    SIZE = auto()
    ISDIR = auto()
    CTIME = auto()
    MTIME = auto()


SortKeyWithOrder = tuple[SortKey, bool]
SortKeyArg = Collection[Union[SortKey, SortKeyWithOrder]]


def normalize_sort_keys(keys: SortKeyArg) -> list[SortKeyWithOrder]:
    ret = []
    for key in keys:
        if isinstance(key, SortKey):
            ret.append((key, False))
        else:
            ret.append(key)
    return ret


class FileSystemStorage(BaseFileSystemStorage):
    def sort_by(self, files: Collection[Path], keys: SortKeyArg) -> list[Path]:
        nkeys = normalize_sort_keys(keys)
        reverse_all = False

        for (key, reverse) in nkeys:
            if key == SortKey.NAME:
                reverse_all = reverse

        def sort_value(p: Path) -> list[Union[str, int, float]]:
            stat = p.stat()
            result: list[Union[str, int, float]] = []
            for (key, reverse) in nkeys:
                reverse = operator.xor(reverse, reverse_all)
                multiplier = -1 if reverse else 1
                if key == SortKey.NAME:
                    result.append(p.name)
                elif key == SortKey.ISDIR:
                    result.append(operator.xor(p.is_dir(), reverse))
                elif key == SortKey.SIZE:
                    if p.is_dir():
                        result.append(0)
                    else:
                        result.append(stat.st_size * multiplier)
                elif key == SortKey.CTIME:
                    result.append(stat.st_ctime * multiplier)
                elif key == SortKey.MTIME:
                    result.append(stat.st_mtime * multiplier)
            return result

        return sorted(files, key=sort_value, reverse=reverse_all)

    def recurse(self, path: Union[Path, str], sort: SortKeyArg = []) -> list[Path]:
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
        return self.sort_by(files, sort)

    def list_recursive(self, path="", sort: SortKeyArg = []) -> list[str]:
        """Recursively lists files in `path`, ordered by `sort`."""
        full_path = self.path(path)
        return [str(p)[len(full_path):].strip("/") for p in self.recurse(full_path, sort)]
