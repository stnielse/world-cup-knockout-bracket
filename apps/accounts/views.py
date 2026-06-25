from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import EmailUserCreationForm


def signup(request):
    if request.method == "POST":
        form = EmailUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("my_groups")
    else:
        form = EmailUserCreationForm()
    return render(request, "accounts/signup.html", {"form": form})
