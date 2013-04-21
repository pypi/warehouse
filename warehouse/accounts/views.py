from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url
from django.views.generic import View
from django.views.generic.base import TemplateResponseMixin

from warehouse.accounts.forms import SignupForm
from warehouse.accounts.regards import UserCreator


class SignupView(TemplateResponseMixin, View):

    creator = UserCreator()
    form_class = SignupForm
    template_name = "accounts/signup.html"

    def post(self, request):
        form = self.form_class(request.POST)
        next = request.REQUEST.get("next", None)

        if form.is_valid():
            # Create User
            self.creator(
                            username=form.cleaned_data["username"],
                            email=form.cleaned_data["email"],
                            password=form.cleaned_data["password"],
                        )

            # Redirect to the next page
            if next is None:
                next = resolve_url(settings.LOGIN_REDIRECT_URL)

            return HttpResponseRedirect(next, status=303)

        return self.render_to_response(dict(form=form, next=next))

    def get(self, request):
        form = self.form_class()
        next = request.REQUEST.get("next", None)

        return self.render_to_response(dict(form=form, next=next))

signup = SignupView.as_view()
