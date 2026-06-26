from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("groups/", views.my_groups, name="my_groups"),
    path("groups/new/", views.create_group, name="create_group"),
    path("groups/join/", views.join_group, name="join_group"),
    path(
        "groups/<int:group_id>/bracket/",
        views.bracket_view,
        name="bracket_view",
    ),
    path(
        "groups/<int:group_id>/bracket/match/<int:match_id>/pick/",
        views.match_pick,
        name="match_pick",
    ),
    path(
        "groups/<int:group_id>/bracket/submit/",
        views.submit_bracket,
        name="submit_bracket",
    ),
    path(
        "groups/<int:group_id>/bracket/unsubmit/",
        views.unsubmit_bracket,
        name="unsubmit_bracket",
    ),
    path(
        "groups/<int:group_id>/leaderboard/",
        views.leaderboard_view,
        name="leaderboard_view",
    ),
]
