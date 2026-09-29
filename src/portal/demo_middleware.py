"""Constrain the disposable public demo to participant, judge and voter workflows."""
from django.http import HttpResponseNotAllowed, HttpResponseRedirect

class InteractiveDemoBoundary:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        # Do not let non-demo users exercise the organizer, staff or token APIs.
        if path.startswith(('/admin/', '/organizer/', '/api/', '/events/')) or path in ('/admin', '/signup/', '/login/') or path.startswith(('/vote/email/', '/vote/open/', '/judge/accept/')):
            return HttpResponseNotAllowed(['GET']) if request.method not in ('GET', 'HEAD') else HttpResponseRedirect('/demo')
        if path.startswith('/tour/'):
            return HttpResponseRedirect('/demo')
        allowed_write = path in ('/demo/enter', '/demo/switch', '/teams/new', '/projects/new', '/vote', '/logout/') or path.startswith(('/judge/score/', '/projects/'))
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and not allowed_write:
            return HttpResponseNotAllowed(['GET', 'HEAD', 'OPTIONS'])
        return self.get_response(request)

class InteractiveDemoRoleBoundary:
    """Apply role restrictions after AuthenticationMiddleware has populated request.user."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.session.get('demo_role') == 'judge':
            if request.path.startswith(('/teams/', '/projects/')) or request.path == '/vote':
                return HttpResponseNotAllowed(['GET', 'HEAD', 'OPTIONS'])
        return self.get_response(request)
