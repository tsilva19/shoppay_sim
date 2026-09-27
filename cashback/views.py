from rest_framework import generics

from .models import CashbackCredit, CashbackRule
from .serializers import CashbackCreditSerializer, CashbackRuleSerializer


class CashbackRuleListView(generics.ListAPIView):
    """Regras de cashback ativas — só para consulta (gerenciadas via /admin/)."""

    queryset = CashbackRule.objects.filter(active=True)
    serializer_class = CashbackRuleSerializer


class MyCashbackCreditsView(generics.ListAPIView):
    serializer_class = CashbackCreditSerializer

    def get_queryset(self):
        return CashbackCredit.objects.filter(wallet=self.request.user.wallet)
