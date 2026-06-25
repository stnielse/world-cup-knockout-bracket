from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import GroupCreateForm, GroupJoinForm
from .models import GroupMembership, Match, Prediction, Team, is_tournament_locked
from .services import build_group_bracket, build_user_bracket, reconcile_user_picks


def home(request):
    if request.user.is_authenticated:
        return redirect("my_groups")
    return redirect("login")


@login_required
def my_groups(request):
    memberships = (
        GroupMembership.objects.filter(user=request.user)
        .select_related("group")
        .order_by("-joined_at")
    )
    return render(request, "bracket/my_groups.html", {"memberships": memberships})


@login_required
def create_group(request):
    if request.method == "POST":
        form = GroupCreateForm(request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.owner = request.user
            group.save()
            GroupMembership.objects.create(group=group, user=request.user)
            return redirect("my_groups")
    else:
        form = GroupCreateForm()
    return render(request, "bracket/group_create.html", {"form": form})


@login_required
def join_group(request):
    if request.method == "POST":
        form = GroupJoinForm(request.POST)
        if form.is_valid():
            GroupMembership.objects.get_or_create(group=form.group, user=request.user)
            return redirect("my_groups")
    else:
        form = GroupJoinForm()
    return render(request, "bracket/group_join.html", {"form": form})


def _get_membership_or_404(user, group_id):
    return get_object_or_404(
        GroupMembership.objects.select_related("group"),
        user=user,
        group_id=group_id,
    )


def _render_user_bracket_swap(request, membership):
    bracket = build_user_bracket(request.user, membership.group)
    return render(
        request,
        "bracket/_user_bracket.html",
        {
            "group": membership.group,
            "membership": membership,
            "bracket": bracket,
        },
    )


@login_required
def bracket_view(request, group_id):
    membership = _get_membership_or_404(request.user, group_id)
    view_mode = request.GET.get("view", "mine")
    if view_mode == "group":
        if not is_tournament_locked():
            return redirect("bracket_view", group_id=group_id)
        bracket = build_group_bracket(membership.group)
    else:
        view_mode = "mine"
        bracket = build_user_bracket(request.user, membership.group)
    return render(
        request,
        "bracket/bracket_view.html",
        {
            "group": membership.group,
            "membership": membership,
            "bracket": bracket,
            "view_mode": view_mode,
            "is_locked": is_tournament_locked(),
        },
    )


@login_required
@require_POST
def match_pick(request, group_id, match_id):
    membership = _get_membership_or_404(request.user, group_id)
    if is_tournament_locked() or membership.bracket_submitted:
        return HttpResponseBadRequest("Bracket is not editable.")

    team_id = request.POST.get("team")
    if not team_id:
        return HttpResponseBadRequest("Missing team.")

    match = get_object_or_404(Match, id=match_id)
    team = get_object_or_404(Team, id=team_id)

    bracket = build_user_bracket(request.user, membership.group)
    target = None
    for round_data in bracket["rounds"]:
        for entry in round_data["matches"]:
            if entry["match"].id == match.id:
                target = entry
                break
        if target:
            break
    if not target or not target["pickable"]:
        return HttpResponseBadRequest("Match not pickable.")
    if team not in (target["home"], target["away"]):
        return HttpResponseBadRequest("Team not in match.")

    Prediction.objects.update_or_create(
        user=request.user,
        group=membership.group,
        match=match,
        defaults={"picked_winner": team},
    )
    reconcile_user_picks(request.user, membership.group)

    return _render_user_bracket_swap(request, membership)


@login_required
@require_POST
def submit_bracket(request, group_id):
    membership = _get_membership_or_404(request.user, group_id)
    if is_tournament_locked() or membership.bracket_submitted:
        return HttpResponseBadRequest("Cannot submit.")
    bracket = build_user_bracket(request.user, membership.group)
    if not bracket["complete"]:
        return HttpResponseBadRequest("Bracket incomplete.")
    membership.bracket_submitted = True
    membership.bracket_submitted_at = timezone.now()
    membership.save(update_fields=["bracket_submitted", "bracket_submitted_at"])
    return _render_user_bracket_swap(request, membership)


@login_required
@require_POST
def unsubmit_bracket(request, group_id):
    membership = _get_membership_or_404(request.user, group_id)
    if is_tournament_locked() or not membership.bracket_submitted:
        return HttpResponseBadRequest("Cannot unsubmit.")
    membership.bracket_submitted = False
    membership.bracket_submitted_at = None
    membership.save(update_fields=["bracket_submitted", "bracket_submitted_at"])
    return _render_user_bracket_swap(request, membership)
