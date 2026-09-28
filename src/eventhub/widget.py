"""Read-only embeddable public gallery widget (T4 UI/export slice).

Owns a single view helper, ``widget_gallery``, that renders the canonical
public project list for one event in a self-contained, iframe-safe page.

Integration route requirement (wired by the core owner, NOT in this patch):
    path('embed/<slug:event_slug>/gallery', widget.widget_gallery,
         name='widget_gallery')

Security contract:
- The event slug is validated with Django's slug validator before any ORM
  use; anything else is a 404. Unknown events are a 404, never a redirect
  or a fallback to another event.
- Only canonical public rows are shown: draft=False and
  duplicate_of__isnull=True, scoped strictly to the requested event. Drafts,
  duplicate submissions, and every other event's projects are invisible.
- The template renders with Django autoescaping on; project/team/track
  text is never marked safe. No judge, score, vote, invite-token, or
  organizer-only field is selected or exposed - this page is read-only
  and shows exactly what the public gallery shows.
- The view performs no writes, touches no session, and sets no cookies.

Embedding / CSP / origin policy:
- The page is frameable by design: X-Frame-Options is exempted and a
  Content-Security-Policy is set whose frame-ancestors directive lists
  the origins allowed to embed it. Configure allowed embedders with the
  WIDGET_FRAME_ANCESTORS setting (default '*' - any site may embed, which
  is acceptable because the page is public, read-only, and carries no
  credentials; an organizer who wants to restrict embedders sets e.g.
  WIDGET_FRAME_ANCESTORS = "'self' https://event.example").
- The widget itself is locked down: default-src 'none', no scripts, no
  forms, no external subresources besides its own stylesheet, so a
  compromised embedder gains nothing from the framed document.
- Recommended host-page embedding:
    <iframe src="https://portal.example/embed/<event-slug>/gallery"
            sandbox="allow-same-origin"
            referrerpolicy="no-referrer"
            style="width:100%;border:0" title="Projects"></iframe>
  The page is responsive: it lays out for whatever width the iframe
  gives it, from phone widths up.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_slug
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_exempt

from .models import Event, Project

WIDGET_CSP = (
    "default-src 'none'; "
    "style-src 'self'; "
    "img-src 'self'; "
    "font-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors {frame_ancestors}"
)


def public_projects(event):
    """Canonical public projects for an event: nondraft, non-duplicate."""
    return (
        Project.objects.filter(event=event, duplicate_of__isnull=True, draft=False)
        .select_related('track', 'team')
        .order_by('title')
    )


@xframe_options_exempt
def widget_gallery(request, event_slug):
    try:
        validate_slug(event_slug)
    except ValidationError:
        raise Http404('Invalid event slug')
    event = get_object_or_404(Event, slug=event_slug)
    theme = request.GET.get('theme', 'light')
    if theme not in ('light', 'dark'):
        theme = 'light'
    response = render(
        request,
        'widget_gallery.html',
        {'event': event, 'projects': public_projects(event), 'theme': theme},
    )
    frame_ancestors = getattr(settings, 'WIDGET_FRAME_ANCESTORS', '*')
    response['Content-Security-Policy'] = WIDGET_CSP.format(
        frame_ancestors=frame_ancestors
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'public, max-age=60'
    return response
