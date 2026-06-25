from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import GroupCreateForm, GroupJoinForm
from .models import GroupMembership


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
