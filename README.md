# groplay-django

A collection of Django stuff that could be useful in various different projects.

## Installation

Add `'groplay'` to `settings.INSTALLED_APPS`. Place it before `'django.contrib.staticfiles'` if you want it to override `collectstatic` (nothing important, just gets rid of some annoying warnings when using Grappelli) and `runserver` (minor file watching improvements).

## Notes on the contents

`groplay.fields` contains model fields, not form fields.

### For use with the admin:

* `groplay.actions`: Admin actions.
* `groplay.admin`: Filters and ModelAdmin mixins.

### For use with Django REST Framework:

* `groplay.permissions`
* `groplay.renderers`
* `groplay.routers`
* `groplay.schemas`: This contains rather extensive additions to the default OpenAPI schema classes. However, the bulk of it was written for DRF versions where that functionality was very much a work in progress. So it may be that some of it is, or will be, obsolete.
* `groplay.serializer_fields`
* `groplay.serializer_mixins`
* `groplay.view_mixins`
* `groplay.views`
