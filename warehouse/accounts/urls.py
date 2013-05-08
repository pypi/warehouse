from django.conf.urls import patterns, url

from warehouse.accounts import views

urlpatterns = patterns("",
    url(r"^login/$", views.LoginView.as_view(), name="accounts.login"),
    url(r"^settings/$",
        views.AccountSettingsView.as_view(),
        name="accounts.settings",
    ),
    url(r"^signup/$", views.signup, name="accounts.signup"),
)
