from django import forms

from .models import Group


class GroupCreateForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ("name",)


class GroupJoinForm(forms.Form):
    join_code = forms.CharField(
        max_length=8,
        widget=forms.TextInput(attrs={"placeholder": "ABC234", "autocomplete": "off"}),
    )

    def clean_join_code(self):
        code = self.cleaned_data["join_code"].strip().upper()
        try:
            self.group = Group.objects.get(join_code=code)
        except Group.DoesNotExist as exc:
            raise forms.ValidationError("No group found with that code.") from exc
        return code
