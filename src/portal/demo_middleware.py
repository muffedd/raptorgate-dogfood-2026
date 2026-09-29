"""Constrain the disposable public demo to participant, judge and voter workflows."""
from django.http import HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse

class InteractiveDemoBoundary:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        # Do not let non-demo users exercise the organizer, staff or token APIs.
        if path.startswith(('/admin/', '/organizer/', '/api/', '/events/', '/embed/', '/receipt/', '/records/', '/certificates/')) or path in ('/admin', '/signup/', '/login/') or path.startswith(('/vote/email/', '/vote/open/', '/judge/accept/')):
            return HttpResponseNotAllowed(['GET']) if request.method not in ('GET', 'HEAD') else HttpResponseRedirect('/demo')
        if path.startswith('/tour/'):
            return HttpResponseRedirect('/demo')
        allowed_write = path in ('/demo/enter', '/demo/switch', '/teams/new', '/projects/new', '/vote', '/logout/') or path.startswith('/judge/score/')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and not allowed_write:
            return HttpResponseNotAllowed(['GET', 'HEAD', 'OPTIONS'])
        return self.get_response(request)

class InteractiveDemoRoleBoundary:
    """Apply role restrictions after AuthenticationMiddleware has populated request.user."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if request.session.get('demo_role') == 'judge':
                if request.path.startswith(('/teams/', '/projects/')) or request.path == '/vote':
                    return HttpResponseNotAllowed(['GET', 'HEAD', 'OPTIONS'])
            if request.path in ('/teams/new', '/projects/new'):
                from eventhub.models import Event, Project, Team
                event = Event.objects.filter(active=True,slug='interactive-demo').first()
                user = request.user
                if not event or not user.is_authenticated or not user.username.startswith('demo-participant-'):
                    return JsonResponse({'error':'Start a participant demo session first'}, status=403)
                if request.path == '/teams/new' and Team.objects.filter(event=event,members=user).exists():
                    return JsonResponse({'error':'One team per demo visitor'}, status=429)
                if request.path == '/projects/new' and Project.objects.filter(event=event,team__members=user).count() >= 1:
                    # Editing an existing canonical project remains allowed; creation is blocked at the view.
                    if not Team.objects.filter(event=event,members=user).exists():
                        return JsonResponse({'error':'Demo team missing'}, status=403)
            if request.path.startswith('/judge/score/') and request.session.get('demo_role') != 'judge':
                return JsonResponse({'error':'Switch to your judge role'}, status=403)
        return self.get_response(request)
