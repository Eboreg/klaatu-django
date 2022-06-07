import inspect

from django.core.files import locks
from django.core.management.base import BaseCommand


class ExclusiveCommand(BaseCommand):
    """
    For management commands that should be blocked from concurrent execution.
    Uses a file lock as an exclusivity check, by default on the file
    containing the command class (which is really the most logical choice).

    Thanks to some ugl^H^H^Hbeautiful monkey patching, child classes don't
    need to implement any new methods or really change anything; just inherit
    this class instead of BaseCommand, and forget about it.
    """
    lockfile: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        setattr(self, "_handle", self.handle)
        setattr(self, "handle", self.real_handle)

    def real_handle(self, *args, **options):
        if hasattr(self, "lockfile"):
            self._lockfile = open(self.lockfile)
        else:
            self._lockfile = open(inspect.getfile(self.__class__))
        if locks.lock(self._lockfile, locks.LOCK_EX | locks.LOCK_NB):
            try:
                return self._handle(*args, **options)
            finally:
                locks.unlock(self._lockfile)
        else:
            self.stderr.write("This command is already running in another process.")

    def _handle(self, *args, **options):
        raise NotImplementedError("Default _handle() should have been overwritten by now?!")
