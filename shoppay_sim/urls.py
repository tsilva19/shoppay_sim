from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),  # login da Browsable API
    path("api/wallet/", include("wallet.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/cashback/", include("cashback.urls")),
]
