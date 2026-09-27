from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from wallet.services import InsufficientFundsError

from . import services
from .models import Boleto, Installment, PixCharge, Purchase
from .serializers import (
    BoletoSerializer,
    InstallmentSerializer,
    PixChargeCreateSerializer,
    PixChargeSerializer,
    PixTransferCreateSerializer,
    PixTransferSerializer,
    PurchaseSerializer,
)


def _wallet(request):
    return request.user.wallet


# ---------------------------------------------------------------------------
# PIX
# ---------------------------------------------------------------------------


class PixChargeListCreateView(generics.ListCreateAPIView):
    """Lista cobranças PIX da carteira ou cria uma nova (ex.: 'adicionar saldo')."""

    def get_queryset(self):
        return PixCharge.objects.filter(wallet=_wallet(self.request)).order_by("-created_at")

    def get_serializer_class(self):
        return PixChargeCreateSerializer if self.request.method == "POST" else PixChargeSerializer

    def create(self, request, *args, **kwargs):
        serializer = PixChargeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        charge = services.create_pix_charge(_wallet(request), **serializer.validated_data)
        return Response(PixChargeSerializer(charge).data, status=status.HTTP_201_CREATED)


class PixChargePayView(APIView):
    """POST /api/payments/pix/charges/<id>/pay/ — simula o pagador escaneando o QR Code."""

    def post(self, request, pk):
        charge = get_object_or_404(PixCharge, pk=pk, wallet=_wallet(request))
        try:
            charge = services.pay_pix_charge(charge)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(PixChargeSerializer(charge).data)


class PixTransferListCreateView(generics.ListCreateAPIView):
    """Envia (ou lista) transferências PIX entre carteiras do sistema."""

    def get_queryset(self):
        wallet = _wallet(self.request)
        from .models import PixTransfer

        return PixTransfer.objects.filter(from_wallet=wallet) | PixTransfer.objects.filter(to_wallet=wallet)

    def get_serializer_class(self):
        return PixTransferCreateSerializer if self.request.method == "POST" else PixTransferSerializer

    def create(self, request, *args, **kwargs):
        serializer = PixTransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transfer = services.create_pix_transfer(_wallet(request), **serializer.validated_data)
        except (ValueError, InsufficientFundsError) as exc:
            raise ValidationError(str(exc)) from exc
        return Response(PixTransferSerializer(transfer).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Boleto
# ---------------------------------------------------------------------------


class BoletoListCreateView(generics.ListCreateAPIView):
    serializer_class = BoletoSerializer

    def get_queryset(self):
        return Boleto.objects.filter(payer_wallet=_wallet(self.request)).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(payer_wallet=_wallet(self.request))


class BoletoPayView(APIView):
    """POST /api/payments/boletos/<id>/pay/"""

    def post(self, request, pk):
        boleto = get_object_or_404(Boleto, pk=pk, payer_wallet=_wallet(request))
        try:
            boleto = services.pay_boleto(boleto)
        except (ValueError, InsufficientFundsError) as exc:
            raise ValidationError(str(exc)) from exc
        return Response(BoletoSerializer(boleto).data)


# ---------------------------------------------------------------------------
# Carnê digital
# ---------------------------------------------------------------------------


class PurchaseListCreateView(generics.ListCreateAPIView):
    serializer_class = PurchaseSerializer

    def get_queryset(self):
        return Purchase.objects.filter(wallet=_wallet(self.request)).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = PurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            purchase = services.create_purchase(_wallet(request), **serializer.validated_data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(PurchaseSerializer(purchase).data, status=status.HTTP_201_CREATED)


class InstallmentPayView(APIView):
    """POST /api/payments/installments/<id>/pay/"""

    def post(self, request, pk):
        installment = get_object_or_404(
            Installment, pk=pk, purchase__wallet=_wallet(request)
        )
        try:
            installment = services.pay_installment(installment)
        except (ValueError, InsufficientFundsError) as exc:
            raise ValidationError(str(exc)) from exc
        return Response(InstallmentSerializer(installment).data)
