from django.conf import settings

def preview_mode(request):
    return {'preview_mode': settings.PREVIEW, 'interactive_demo': settings.DEMO}
