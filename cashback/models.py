from django.db import models

from payments.models import Purchase
from wallet.models import Wallet


class CashbackRule(models.Model):
    """Regra simples: X% de volta em compras acima de um valor mínimo."""

    name = models.CharField(max_length=100)
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="Ex.: 5.00 para 5%"
    )
    min_purchase_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-percentage"]

    def __str__(self):
        return f"{self.name} ({self.percentage}% acima de R$ {self.min_purchase_amount})"


class CashbackCredit(models.Model):
    """Registro de cashback efetivamente creditado na carteira."""

    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="cashback_credits"
    )
    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name="cashback_credits"
    )
    rule = models.ForeignKey(
        CashbackRule, on_delete=models.SET_NULL, null=True, related_name="credits"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cashback R$ {self.amount} — {self.purchase.merchant}"
