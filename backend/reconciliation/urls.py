from django.urls import path

from .api import (
    ApproveMatchView,
    IgnoreTransactionView,
    ImportView,
    LineItemsView,
    RejectMatchView,
    TransactionsView,
)

urlpatterns = [
    path("import/", ImportView.as_view(), name="statement-import"),
    path("transactions/", TransactionsView.as_view(), name="transactions"),
    path("transactions/<int:transaction_id>/ignore/", IgnoreTransactionView.as_view(), name="ignore-transaction"),
    path("line-items/", LineItemsView.as_view(), name="line-items"),
    path("matches/<int:match_id>/approve/", ApproveMatchView.as_view(), name="approve-match"),
    path("matches/<int:match_id>/reject/", RejectMatchView.as_view(), name="reject-match"),
]
