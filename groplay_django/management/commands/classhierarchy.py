from typing import Dict, List

from django.core.management.base import BaseCommand, CommandParser
from django.utils.module_loading import import_string


class Command(BaseCommand):
    classes: Dict[type, List[type]] = {}
    help = 'Outputs a reverse inheritance tree for a class.'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('class_path', help='Full path (period-separated) of a class.')

    def handle(self, *args, **options):
        start = import_string(options['class_path'])
        self.get_bases(start)
        self.print_class(start)

    def get_bases(self, klass: type):
        if klass not in self.classes:
            bases = [b for b in klass.__bases__ if b is not object]
            self.classes[klass] = bases
            for base in bases:
                self.get_bases(base)

    def print_class(self, klass: type, depth=0, prefix='', is_last_child=False):
        if depth:
            self.stdout.write(prefix, ending='')
            if is_last_child:
                self.stdout.write('└── ', ending='')
            else:
                self.stdout.write('├── ', ending='')

        self.stdout.write(f'{klass.__module__}.{klass.__name__}')

        if not depth:
            child_prefix = ''
        elif is_last_child:
            child_prefix = prefix + '    '
        else:
            child_prefix = prefix + '│   '

        children = self.classes.get(klass, [])

        for idx, child in enumerate(children):
            self.print_class(child, depth + 1, child_prefix, idx == len(children) - 1)
