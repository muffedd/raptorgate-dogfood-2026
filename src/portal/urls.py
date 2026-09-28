from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from eventhub import views
urlpatterns=[
 path('admin/',admin.site.urls),
 path('login/',auth_views.LoginView.as_view(template_name='login.html'),name='login'),
 path('logout/',auth_views.LogoutView.as_view(),name='logout'),
 path('',views.home,name='home'),
 path('projects',views.gallery,name='gallery'),
 path('projects/new',views.submit,name='submit'),
 path('api/judge/scores',views.judge_scores,name='judge_scores'),
 path('api/export.csv',views.export_csv,name='export_csv'),
]
