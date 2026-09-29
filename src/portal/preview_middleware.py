"""Public preview displays pages only; no account, vote or organizer mutations."""
from django.http import HttpResponseNotAllowed

class PreviewReadOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            return HttpResponseNotAllowed(['GET', 'HEAD', 'OPTIONS'])
        return self.get_response(request)
