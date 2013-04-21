from django.conf.urls import patterns, url

from warehouse.accounts import views

urlpatterns = patterns("",
    url(r"^signup/$", views.signup, name="accounts.signup"),
)
