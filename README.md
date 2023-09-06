# groplay-django

A collection of Django stuff that could be useful in various different projects.

## Installation

Add `'groplay_django'` to `settings.INSTALLED_APPS`. Place it before `'django.contrib.staticfiles'` if you want it to override `collectstatic` (nothing important, just gets rid of some annoying warnings when using Grappelli) and `runserver` (minor file watching improvements).

## Notes on the contents

`groplay_django.fields` contains model fields, not form fields.

### For use with the admin:

* `groplay_django.actions`: Admin actions.
* `groplay_django.admin`: Filters and ModelAdmin mixins.

### For use with Django REST Framework:

* `groplay_django.permissions`
* `groplay_django.renderers`
* `groplay_django.routers`
* `groplay_django.schemas`: This contains rather extensive additions to the default OpenAPI schema classes. However, the bulk of it was written for DRF versions where that functionality was very much a work in progress. So it may be that some of it is, or will be, obsolete.
* `groplay_django.serializer_fields`
* `groplay_django.serializer_mixins`
* `groplay_django.view_mixins`
* `groplay_django.views`
