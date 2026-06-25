from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("groups/", views.my_groups, name="my_groups"),
    path("groups/new/", views.create_group, name="create_group"),
    path("groups/join/", views.join_group, name="join_group"),
]
