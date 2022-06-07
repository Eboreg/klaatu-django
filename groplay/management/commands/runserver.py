import logging
import os
import signal
import sys
from pathlib import Path

import django
from django.contrib.staticfiles.management.commands.runserver import Command as RunServerCommand
from django.utils import autoreload

DJANGO_AUTORELOAD_ENV = 'RUN_MAIN'

logger = logging.getLogger('django.utils.autoreload')


class WatchmanReloader(autoreload.WatchmanReloader):
    """
    Don't watch /usr and /etc, mainly since Watchman constantly believes
    /etc/python3.8/sitecustomize.py has been changed for some reason.

    Don't watch anything in a venv package either, for performance reasons.
    """
    def watched_files(self, include_globs):
        for f in super().watched_files(include_globs=include_globs):
            if (
                not f.as_posix().startswith('/usr') and
                not f.as_posix().startswith('/etc') and
                not Path(django.__file__).parent.parent in f.parents
            ):
                yield f


class Command(RunServerCommand):
    def run(self, **options):
        if options['use_reloader']:
            run_with_reloader(self.inner_run, **options)  # type: ignore
        else:
            self.inner_run(None, **options)  # type: ignore


def get_reloader():
    """Return the most suitable reloader for this environment."""
    try:
        WatchmanReloader.check_availability()
    except autoreload.WatchmanUnavailable:
        return autoreload.StatReloader()
    return WatchmanReloader()


def run_with_reloader(main_func, *args, **kwargs):
    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    try:
        if os.environ.get(DJANGO_AUTORELOAD_ENV) == 'true':
            reloader = get_reloader()
            logger.info('Watching for file changes with %s', reloader.__class__.__name__)
            autoreload.start_django(reloader, main_func, *args, **kwargs)
        else:
            exit_code = autoreload.restart_with_reloader()
            sys.exit(exit_code)
    except KeyboardInterrupt:
        pass
