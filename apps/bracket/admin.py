from django.contrib import admin

from .models import (
    Group,
    GroupMembership,
    Match,
    Prediction,
    ScoringRule,
    Team,
)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "flag_emoji")
    search_fields = ("code", "name")
    ordering = ("name",)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "slot",
        "round",
        "home_team",
        "away_team",
        "kickoff_at",
        "winner",
        "feeds_into",
        "feeds_as",
    )
    list_filter = ("round",)
    search_fields = ("slot", "home_team__code", "away_team__code")
    autocomplete_fields = ("home_team", "away_team", "winner", "feeds_into")
    ordering = ("kickoff_at", "slot")


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "join_code", "owner", "created_at")
    search_fields = ("name", "join_code", "owner__email")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at",)


@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    list_display = ("group", "user", "joined_at")
    search_fields = ("group__name", "user__email")
    autocomplete_fields = ("group", "user")
    readonly_fields = ("joined_at",)


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "match", "picked_winner", "updated_at")
    list_filter = ("group", "match__round")
    search_fields = ("user__email", "group__name", "match__slot")
    autocomplete_fields = ("user", "group", "match", "picked_winner")
    readonly_fields = ("updated_at",)


@admin.register(ScoringRule)
class ScoringRuleAdmin(admin.ModelAdmin):
    list_display = ("round", "points")
    ordering = ("round",)
