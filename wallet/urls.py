from django.urls import path

from . import views

app_name = "wallet"

urlpatterns = [
    path("me/", views.MyWalletView.as_view(), name="me"),
    path("transactions/", views.MyTransactionsView.as_view(), name="transactions"),
]
