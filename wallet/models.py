import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Wallet(models.Model):
    """Carteira digital do usuário — equivalente à conta ShopPay."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet"
    )
    pix_key = models.CharField(max_length=64, unique=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Carteira de {self.user.get_username()} (R$ {self.balance})"


class Transaction(models.Model):
    """Extrato da carteira — todo débito/crédito passa por aqui."""

    class Kind(models.TextChoices):
        CREDIT = "CREDIT", "Crédito"
        DEBIT = "DEBIT", "Débito"

    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="transactions"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)

    # Referência genérica para o que originou a transação
    # (PixCharge, PixTransfer, Boleto, Installment, CashbackCredit...)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source = GenericForeignKey("content_type", "object_id")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.kind == self.Kind.CREDIT else "-"
        return f"{sign}R$ {self.amount} — {self.description}"


def generate_pix_key() -> str:
    return str(uuid.uuid4())
