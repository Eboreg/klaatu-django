from rest_framework.renderers import BrowsableAPIRenderer as BaseBrowsableAPIRenderer


class BrowsableAPIRenderer(BaseBrowsableAPIRenderer):
    def get_filter_form(self, data, view, request):
        # Just to get rid of those pesky duplicate DB hits that make it
        # harder to debug and optimize.
        return None
