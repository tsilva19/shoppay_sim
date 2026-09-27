from decimal import Decimal

from rest_framework import serializers

from .models import Boleto, Installment, PixCharge, PixTransfer, Purchase


class PixChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PixCharge
        fields = [
            "id",
            "amount",
            "description",
            "e2e_id",
            "payload",
            "status",
            "created_at",
            "expires_at",
            "paid_at",
        ]
        read_only_fields = [
            "id", "e2e_id", "payload", "status", "created_at", "expires_at", "paid_at"
        ]


class PixChargeCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)


class PixTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = PixTransfer
        fields = ["id", "from_wallet", "to_wallet", "amount", "description", "status", "e2e_id", "created_at"]
        read_only_fields = fields


class PixTransferCreateSerializer(serializers.Serializer):
    to_pix_key = serializers.CharField(max_length=64)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)


class BoletoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Boleto
        fields = ["id", "description", "amount", "barcode", "due_date", "status", "created_at", "paid_at"]
        read_only_fields = ["id", "barcode", "status", "created_at", "paid_at"]


class InstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Installment
        fields = ["id", "number", "amount", "due_date", "status", "paid_at"]
        read_only_fields = fields


class PurchaseSerializer(serializers.ModelSerializer):
    installments = InstallmentSerializer(many=True, read_only=True)

    class Meta:
        model = Purchase
        fields = ["id", "merchant", "total_amount", "installments_count", "created_at", "installments"]
        read_only_fields = ["id", "created_at", "installments"]
