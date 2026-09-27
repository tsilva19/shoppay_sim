from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("pix/charges/", views.PixChargeListCreateView.as_view(), name="pix-charge-list"),
    path("pix/charges/<int:pk>/pay/", views.PixChargePayView.as_view(), name="pix-charge-pay"),
    path("pix/transfers/", views.PixTransferListCreateView.as_view(), name="pix-transfer-list"),
    path("boletos/", views.BoletoListCreateView.as_view(), name="boleto-list"),
    path("boletos/<int:pk>/pay/", views.BoletoPayView.as_view(), name="boleto-pay"),
    path("purchases/", views.PurchaseListCreateView.as_view(), name="purchase-list"),
    path("installments/<int:pk>/pay/", views.InstallmentPayView.as_view(), name="installment-pay"),
]
