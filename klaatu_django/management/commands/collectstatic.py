from django.contrib.staticfiles.management.commands.collectstatic import Command as BaseCommand


class Command(BaseCommand):
    def log(self, msg: str, level: int = 2):
        """
        MAJESTICALLY ugly hack to avoid all the annoying "Found another file"
        messages that are an unavoidable result of running Grappelli.
        """
        if not msg.startswith('Found another file with the destination path'):
            super().log(msg, level=level)
