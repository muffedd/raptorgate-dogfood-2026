"""Public preview displays pages only; no account, vote or organizer mutations."""
from django.http import HttpResponseNotAllowed, HttpResponseRedirect

class PreviewReadOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            return HttpResponseNotAllowed(['GET', 'HEAD', 'OPTIONS'])
        if request.path in ('/ballot', '/signup/', '/login/', '/admin/') or request.path.startswith(('/organizer/', '/judge/', '/teams/')):
            return HttpResponseRedirect('/projects')
        return self.get_response(request)
