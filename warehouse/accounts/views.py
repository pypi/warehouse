from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url
from django.views.generic import View
from django.views.generic.base import TemplateResponseMixin
from django.utils.http import is_safe_url
from django.utils.translation import ugettext as _

from django.contrib.auth import authenticate, login as auth_login

from warehouse.accounts.forms import LoginForm, SignupForm
from warehouse.accounts.regards import UserCreator


class LoginView(TemplateResponseMixin, View):

    authenticator = staticmethod(authenticate)
    login = staticmethod(auth_login)
    form_class = LoginForm
    template_name = "accounts/login.html"

    def dispatch(self, request, *args, **kwargs):
        # If the user is already logged in, redirect them
        if request.user.is_authenticated():
            return HttpResponseRedirect(self._get_next_url(request),
                        status=303,
                    )
        return super(LoginView, self).dispatch(request, *args, **kwargs)

    def post(self, request):
        form = self.form_class(request.POST)
        next_url = request.REQUEST.get("next", None)

        if form.is_valid():
            # Attempt to authenticate the user
            user = self.authenticator(
                        username=form.cleaned_data["username"],
                        password=form.cleaned_data["password"],
                    )

            if user is not None:
                # We have a valid user, so add their session to the request
                self.login(request, user)

                return HttpResponseRedirect(self._get_next_url(request),
                            status=303,
                        )

            # We don't have a valid user, so send an error back to the form
            m = _("Invalid username or password")
            form._errors.setdefault("__all__", form.error_class([])).append(m)

        return self.render_to_response(dict(form=form, next=next_url))

    def get(self, request):
        form = self.form_class()
        next_url = request.REQUEST.get("next", None)

        return self.render_to_response(dict(form=form, next=next_url))

    def _get_next_url(self, request):
        next_url = request.REQUEST.get("next", None)
        if not is_safe_url(next_url, host=request.get_host()):
            next_url = resolve_url(settings.LOGIN_REDIRECT_URL)
        return next_url


class SignupView(TemplateResponseMixin, View):

    creator = UserCreator()
    form_class = SignupForm
    template_name = "accounts/signup.html"

    def post(self, request):
        form = self.form_class(request.POST)
        next_url = request.REQUEST.get("next", None)

        if form.is_valid():
            # Create User
            self.creator(
                            username=form.cleaned_data["username"],
                            email=form.cleaned_data["email"],
                            password=form.cleaned_data["password"],
                        )

            # Redirect to the next page
            if not is_safe_url(next_url, host=request.get_host()):
                next_url = resolve_url(settings.LOGIN_REDIRECT_URL)

            return HttpResponseRedirect(next_url, status=303)

        return self.render_to_response(dict(form=form, next=next_url))

    def get(self, request):
        form = self.form_class()
        next_url = request.REQUEST.get("next", None)

        return self.render_to_response(dict(form=form, next=next_url))

signup = SignupView.as_view()
