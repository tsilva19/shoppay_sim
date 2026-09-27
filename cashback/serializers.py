from rest_framework import serializers

from .models import CashbackCredit, CashbackRule


class CashbackRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashbackRule
        fields = ["id", "name", "percentage", "min_purchase_amount", "active"]
        read_only_fields = fields


class CashbackCreditSerializer(serializers.ModelSerializer):
    merchant = serializers.CharField(source="purchase.merchant", read_only=True)

    class Meta:
        model = CashbackCredit
        fields = ["id", "purchase", "merchant", "amount", "created_at"]
        read_only_fields = fields
