# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
