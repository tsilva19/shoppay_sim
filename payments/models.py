import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from wallet.models import Wallet


def generate_e2e_id() -> str:
    """Simula o formato de um endToEndId de PIX: E + 32 dígitos."""
    return "E" + uuid.uuid4().hex + uuid.uuid4().hex[:11]


def generate_barcode() -> str:
    """Simula uma linha digitável de boleto (47 dígitos), sem validar DV real."""
    return "".join(str(uuid.uuid4().int)[:1] for _ in range(47))


# ---------------------------------------------------------------------------
# PIX
# ---------------------------------------------------------------------------


class PixCharge(models.Model):
    """Cobrança PIX (QR Code) — usada para 'adicionar saldo' ou receber de terceiros."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Aguardando pagamento"
        PAID = "PAID", "Pago"
        EXPIRED = "EXPIRED", "Expirado"

    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="pix_charges"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    e2e_id = models.CharField(max_length=64, unique=True, default=generate_e2e_id)
    payload = models.CharField(max_length=255, editable=False)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=30)
        if not self.payload:
            # BR Code fake, só para parecer um payload PIX real (não é EMV válido)
            self.payload = f"00020126PIXSIM{self.e2e_id[:20]}5204000053039865802BR"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"PIX R$ {self.amount} ({self.get_status_display()})"


class PixTransfer(models.Model):
    """Transferência PIX entre duas carteiras simuladas do sistema."""

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Concluída"
        FAILED = "FAILED", "Falhou"

    from_wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="pix_transfers_sent"
    )
    to_wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="pix_transfers_received"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    e2e_id = models.CharField(max_length=64, unique=True, default=generate_e2e_id)
    status = models.CharField(max_length=10, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PIX {self.from_wallet} -> {self.to_wallet}: R$ {self.amount}"


# ---------------------------------------------------------------------------
# Boleto
# ---------------------------------------------------------------------------


class Boleto(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Em aberto"
        PAID = "PAID", "Pago"
        OVERDUE = "OVERDUE", "Vencido"

    payer_wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="boletos"
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    barcode = models.CharField(max_length=47, unique=True, default=generate_barcode)
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def refresh_status(self):
        """Marca como vencido se passou da data e ainda não foi pago."""
        if self.status == self.Status.PENDING and self.due_date < timezone.localdate():
            self.status = self.Status.OVERDUE
            self.save(update_fields=["status"])

    def __str__(self):
        return f"Boleto {self.description} — R$ {self.amount} ({self.get_status_display()})"


# ---------------------------------------------------------------------------
# Carnê digital (compra parcelada)
# ---------------------------------------------------------------------------


class Purchase(models.Model):
    """Uma compra feita 'no app', que pode ser parcelada no carnê digital."""

    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="purchases"
    )
    merchant = models.CharField(max_length=255)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    installments_count = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Compra em {self.merchant} — R$ {self.total_amount} ({self.installments_count}x)"


class Installment(models.Model):
    """Uma parcela do carnê digital."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Em aberto"
        PAID = "PAID", "Paga"
        OVERDUE = "OVERDUE", "Vencida"

    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name="installments"
    )
    number = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        unique_together = ("purchase", "number")

    def refresh_status(self):
        if self.status == self.Status.PENDING and self.due_date < timezone.localdate():
            self.status = self.Status.OVERDUE
            self.save(update_fields=["status"])

    def __str__(self):
        return f"Parcela {self.number}/{self.purchase.installments_count} — R$ {self.amount}"
