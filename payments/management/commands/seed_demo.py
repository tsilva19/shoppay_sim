from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from cashback.models import CashbackRule
from cashback.services import apply_cashback
from payments import services as payments_services

User = get_user_model()


class Command(BaseCommand):
    help = "Popula o banco com usuários, carteiras, PIX, boleto, carnê e cashback de exemplo."

    def handle(self, *args, **options):
        thiago, created = User.objects.get_or_create(
            username="thiago", defaults={"email": "thiago@example.com"}
        )
        if created:
            thiago.set_password("thiago123")
            thiago.save()
            self.stdout.write(self.style.SUCCESS("Usuário 'thiago' criado (senha: thiago123)"))

        loja, created = User.objects.get_or_create(
            username="loja_parceira", defaults={"email": "loja@example.com"}
        )
        if created:
            loja.set_password("loja123")
            loja.save()
            self.stdout.write(self.style.SUCCESS("Usuário 'loja_parceira' criado (senha: loja123)"))

        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin123")
            self.stdout.write(self.style.SUCCESS("Superusuário 'admin' criado (senha: admin123)"))

        # Regra de cashback: 5% acima de R$ 50
        rule, _ = CashbackRule.objects.get_or_create(
            name="Cashback padrão",
            defaults={"percentage": Decimal("5.00"), "min_purchase_amount": Decimal("50.00")},
        )

        thiago_wallet = thiago.wallet
        loja_wallet = loja.wallet

        # 1) PIX: Thiago adiciona saldo (cobrança PIX paga por ele mesmo, simulando um "cash-in")
        charge = payments_services.create_pix_charge(
            thiago_wallet, Decimal("500.00"), "Adicionar saldo via PIX"
        )
        payments_services.pay_pix_charge(charge)

        # 2) PIX: Thiago paga a loja parceira
        payments_services.create_pix_transfer(
            thiago_wallet, loja_wallet.pix_key, Decimal("35.90"), "Compra de café"
        )

        # 3) Boleto em aberto para Thiago pagar
        payments_services.create_boleto(
            thiago_wallet,
            Decimal("120.00"),
            (timezone.localdate() + timedelta(days=10)),
            "Conta de energia",
        )

        # 4) Compra parcelada (carnê digital) com cashback automático
        payments_services.create_purchase(
            thiago_wallet, "Loja Parceira Eletrônicos", Decimal("300.00"), installments_count=3
        )

        self.stdout.write(self.style.SUCCESS("Dados de exemplo criados com sucesso."))
        self.stdout.write(f"Saldo de thiago: R$ {thiago_wallet.balance}")
        thiago_wallet.refresh_from_db()
        self.stdout.write(f"Saldo de thiago (atualizado): R$ {thiago_wallet.balance}")
        self.stdout.write(f"Chave PIX de thiago: {thiago_wallet.pix_key}")
        self.stdout.write(f"Chave PIX da loja_parceira: {loja_wallet.pix_key}")
