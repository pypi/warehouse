from django.conf.urls import patterns, url

from warehouse.accounts import views

urlpatterns = patterns("",
    url(r"^login/$", views.LoginView.as_view(), name="accounts.login"),
    url(r"^settings/$",
        views.AccountSettingsView.as_view(),
        name="accounts.settings",
    ),
    url(r"^settings/set-primary-email/(?P<email>[^/@]+@[^/@]+)/$",
        views.SetPrimaryEmailView.as_view(),
        name="accounts.set-primary-email",
    ),
    url(r"^settings/delete-email/(?P<email>[^/@]+@[^/@]+)/$",
        views.DeleteAccountEmailView.as_view(),
        name="accounts.delete-email",
    ),
    url(r"^signup/$", views.signup, name="accounts.signup"),
)
