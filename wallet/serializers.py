from rest_framework import serializers

from .models import Transaction, Wallet


class WalletSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "username", "pix_key", "balance", "created_at"]
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    source_type = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id",
            "kind",
            "amount",
            "balance_after",
            "description",
            "source_type",
            "created_at",
        ]
        read_only_fields = fields

    def get_source_type(self, obj):
        return obj.content_type.model if obj.content_type_id else None
