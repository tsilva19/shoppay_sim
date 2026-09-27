from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Transaction
from .serializers import TransactionSerializer, WalletSerializer


class MyWalletView(APIView):
    """GET /api/wallet/me/ — dados da carteira do usuário autenticado."""

    def get(self, request):
        serializer = WalletSerializer(request.user.wallet)
        return Response(serializer.data)


class MyTransactionsView(generics.ListAPIView):
    """GET /api/wallet/transactions/ — extrato da carteira do usuário autenticado."""

    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.filter(wallet=self.request.user.wallet)
