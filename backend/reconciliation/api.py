from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BankTransaction, LineItem, Match, Organization
from .services import approve_match, import_statement


def money(value):
    return f"{value:.2f}"


def match_data(match):
    item = match.line_item
    return {
        "id": match.id,
        "status": match.status,
        "reason": match.reason,
        "line_item_id": item.id,
        "investor_name": item.investor.name,
        "expected_reference": item.expected_reference,
        "amount_called": money(item.amount_called),
        "amount_remaining": money(item.remaining),
    }


def transaction_data(row):
    return {
        "id": row.id,
        "date": row.date.isoformat(),
        "description": row.description,
        "amount": money(row.amount),
        "type": row.kind,
        "reference": row.bank_reference,
        "status": row.status,
        "review_reason": row.review_reason,
        "matches": [match_data(match) for match in row.matches.select_related("line_item__investor").all()],
    }


class OrganizationAPIView(APIView):
    def organization(self, request):
        slug = request.headers.get("X-Organization", "").strip()
        if not slug:
            return None, Response({"error": "X-Organization header is required."}, status=400)
        organization = Organization.objects.filter(slug=slug).first()
        if organization is None:
            return None, Response({"error": "Organization not found."}, status=404)
        return organization, None


class ImportView(OrganizationAPIView):
    def post(self, request):
        organization, error = self.organization(request)
        if error:
            return error
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"error": "Upload a CSV file in the 'file' field."}, status=400)
        if uploaded_file.size > 10 * 1024 * 1024:
            return Response({"error": "CSV file must be 10 MB or smaller."}, status=400)
        try:
            summary, status = import_statement(uploaded_file, organization)
        except UnicodeDecodeError:
            return Response({"error": "CSV must be UTF-8 encoded."}, status=400)
        return Response(summary, status=status)


class TransactionsView(OrganizationAPIView):
    def get(self, request):
        organization, error = self.organization(request)
        if error:
            return error
        rows = BankTransaction.objects.filter(organization=organization).prefetch_related(
            "matches__line_item__investor"
        ).order_by("-date", "-id")
        return Response([transaction_data(row) for row in rows])


class LineItemsView(OrganizationAPIView):
    def get(self, request):
        organization, error = self.organization(request)
        if error:
            return error
        items = LineItem.objects.filter(capital_call__organization=organization).select_related(
            "investor", "capital_call"
        ).order_by("capital_call__number", "investor__name")
        return Response([{
            "id": item.id,
            "call_number": item.capital_call.number,
            "call_date": item.capital_call.call_date.isoformat(),
            "due_date": item.capital_call.due_date.isoformat(),
            "investor_name": item.investor.name,
            "expected_reference": item.expected_reference,
            "amount_called": money(item.amount_called),
            "amount_funded": money(item.amount_funded),
            "remaining": money(item.remaining),
            "status": item.status,
        } for item in items])


class MatchActionView(OrganizationAPIView):
    action = None

    def post(self, request, match_id):
        organization, error = self.organization(request)
        if error:
            return error
        if self.action == "approve":
            match, issue = approve_match(match_id, organization)
            if issue == "not_found":
                return Response({"error": "Proposed match not found."}, status=404)
            if issue:
                return Response({"error": "Match can no longer be approved."}, status=409)
            return Response({"match": match.id, "status": match.status})

        match = Match.objects.select_related("transaction").filter(
            pk=match_id, transaction__organization=organization
        ).first()
        if match is None:
            return Response({"error": "Match not found."}, status=404)
        if match.status != Match.Status.PROPOSED:
            return Response({"error": "Only a proposed match can be rejected."}, status=409)
        with transaction.atomic():
            match.status = Match.Status.REJECTED
            match.save(update_fields=["status"])
            if not Match.objects.filter(transaction=match.transaction, status=Match.Status.PROPOSED).exists():
                match.transaction.status = BankTransaction.Status.REVIEW
                if not match.transaction.review_reason:
                    match.transaction.review_reason = "All suggested matches were rejected."
                match.transaction.save(update_fields=["status", "review_reason"])
        return Response({"match": match.id, "status": match.status})


class ApproveMatchView(MatchActionView):
    action = "approve"


class RejectMatchView(MatchActionView):
    action = "reject"


class IgnoreTransactionView(OrganizationAPIView):
    def post(self, request, transaction_id):
        organization, error = self.organization(request)
        if error:
            return error
        row = BankTransaction.objects.filter(pk=transaction_id, organization=organization).first()
        if row is None:
            return Response({"error": "Transaction not found."}, status=404)
        if row.status not in {BankTransaction.Status.SUGGESTED, BankTransaction.Status.REVIEW}:
            return Response({"error": "Only suggested or needs-review transactions can be ignored."}, status=409)
        with transaction.atomic():
            row.status = BankTransaction.Status.IGNORED
            row.review_reason = ""
            row.save(update_fields=["status", "review_reason"])
            Match.objects.filter(transaction=row).exclude(status=Match.Status.REJECTED).update(status=Match.Status.REJECTED)
        return Response({"transaction": row.id, "status": row.status})
