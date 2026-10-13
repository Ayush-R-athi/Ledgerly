from datetime import date
from decimal import Decimal
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from reconciliation.models import BankTransaction, LineItem, Match, Organization


class ReconciliationAPITests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        self.northwind = Organization.objects.get(slug="northwind")
        self.bluebird = Organization.objects.get(slug="bluebird")
        self.client = APIClient()

    def upload(self, csv_text, organization="northwind"):
        file = SimpleUploadedFile("statement.csv", csv_text.encode("utf-8"), content_type="text/csv")
        return self.client.post("/api/import/", {"file": file}, format="multipart", HTTP_X_ORGANIZATION=organization)

    def test_missing_column_rejects_file_without_saving(self):
        response = self.upload("date,description,amount,type\n2026-04-03,wire,10.00,credit\n")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["imported"], 0)
        self.assertTrue(response.data["file_rejected"])
        self.assertFalse(BankTransaction.objects.exists())

    def test_decimal_parsing_and_row_validation(self):
        response = self.upload(
            "date,description,amount,type,reference\n"
            '2026-04-03,WIRE CC-1002,"25,000.00",credit,AMOUNT1\n'
            "2026-04-03,BAD CREDIT,-2.00,credit,BADSIGN\n"
            "2026-04-03,BAD DEBIT,2.00,debit,BADSIGN2\n"
            "2026-02-30,BAD DATE,2.00,credit,BADDATE\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["imported"], 1)
        self.assertEqual([error["line"] for error in response.data["errors"]], [3, 4, 5])
        saved = BankTransaction.objects.get(bank_reference="AMOUNT1")
        self.assertIsInstance(saved.amount, Decimal)
        self.assertEqual(saved.amount, Decimal("25000.00"))

    def test_duplicate_upload_and_duplicate_inside_file(self):
        csv_text = (
            "date,description,amount,type,reference\n"
            "2026-04-03,UNKNOWN WIRE,10.00,credit,DUPE1\n"
            "2026-04-03,SECOND UNKNOWN,20.00,credit,DUPE1\n"
        )
        first = self.upload(csv_text)
        self.assertEqual(first.data["imported"], 1)
        self.assertEqual(first.data["duplicates"], 1)
        single_row = "\n".join(csv_text.splitlines()[:2]) + "\n"
        second = self.upload(single_row)
        self.assertEqual(second.data["imported"], 0)
        self.assertEqual(second.data["duplicates"], 1)

    def test_reference_match_normalization_and_partial_payment(self):
        response = self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-03,WIRE REF cc1001,20000.00,credit,PARTIAL1\n"
        )
        self.assertEqual(response.data["imported"], 1)
        row = BankTransaction.objects.get(bank_reference="PARTIAL1")
        match = row.matches.get()
        self.assertEqual(row.status, BankTransaction.Status.SUGGESTED)
        self.assertEqual(match.line_item.expected_reference, "CC-1001")
        self.assertIn("Reference CC-1001 found", match.reason)

    def test_name_and_exact_remaining_amount_match(self):
        response = self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-07,WIRE INCOMING PATEL FAMILY TRUST,12500.00,credit,NAME1\n"
        )
        row = BankTransaction.objects.get(bank_reference="NAME1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(row.status, BankTransaction.Status.SUGGESTED)
        self.assertEqual(row.matches.get().line_item.expected_reference, "CC-1003")
        self.assertIn("Investor name", row.matches.get().reason)

    def test_ambiguous_name_and_amount_proposes_all_candidates(self):
        original = LineItem.objects.get(expected_reference="CC-1003")
        second_call = original.capital_call.__class__.objects.create(
            organization=self.northwind, number=3,
            call_date=date(2026, 4, 1), due_date=date(2026, 4, 30),
        )
        LineItem.objects.create(
            capital_call=second_call, investor=original.investor,
            expected_reference="CC-1007", amount_called=Decimal("12500.00"),
        )
        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-08,PATEL FAMILY TRUST,12500.00,credit,AMBIG1\n"
        )
        row = BankTransaction.objects.get(bank_reference="AMBIG1")
        self.assertEqual(row.status, BankTransaction.Status.REVIEW)
        self.assertEqual(row.matches.filter(status=Match.Status.PROPOSED).count(), 2)
        self.assertTrue(row.review_reason)

    def test_overpayment_needs_review_without_a_match(self):
        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-03,WIRE CC-1001,30000.00,credit,OVER1\n"
        )
        row = BankTransaction.objects.get(bank_reference="OVER1")
        self.assertEqual(row.status, BankTransaction.Status.REVIEW)
        self.assertFalse(row.matches.exists())
        self.assertIn("exceeds remaining", row.review_reason)

    def test_debit_is_imported_as_ignored(self):
        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-05,BANK FEE,-25.00,debit,FEE1\n"
        )
        row = BankTransaction.objects.get(bank_reference="FEE1")
        self.assertEqual(row.status, BankTransaction.Status.IGNORED)
        self.assertFalse(row.matches.exists())

    def test_reject_last_proposal_moves_transaction_to_review(self):
        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-03,WIRE CC-1001,20000.00,credit,REJECT1\n"
        )
        row = BankTransaction.objects.get(bank_reference="REJECT1")
        response = self.client.post(
            f"/api/matches/{row.matches.get().id}/reject/", HTTP_X_ORGANIZATION="northwind"
        )
        row.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(row.status, BankTransaction.Status.REVIEW)
        self.assertTrue(row.review_reason)

    def test_ignore_rejects_proposals_and_reconciled_transaction_cannot_be_ignored(self):
        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-03,WIRE CC-1001,20000.00,credit,IGNORE1\n"
        )
        row = BankTransaction.objects.get(bank_reference="IGNORE1")
        ignored = self.client.post(
            f"/api/transactions/{row.id}/ignore/", HTTP_X_ORGANIZATION="northwind"
        )
        row.refresh_from_db()
        self.assertEqual(ignored.status_code, 200)
        self.assertEqual(row.status, BankTransaction.Status.IGNORED)
        self.assertEqual(row.matches.get().status, Match.Status.REJECTED)

        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-03,WIRE CC-1002,25000.00,credit,IGNORE2\n"
        )
        row2 = BankTransaction.objects.get(bank_reference="IGNORE2")
        self.client.post(f"/api/matches/{row2.matches.get().id}/approve/", HTTP_X_ORGANIZATION="northwind")
        response = self.client.post(
            f"/api/transactions/{row2.id}/ignore/", HTTP_X_ORGANIZATION="northwind"
        )
        self.assertEqual(response.status_code, 409)

    def test_approval_rechecks_remaining_amount(self):
        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-03,WIRE CC-1002,20000.00,credit,STALE1\n"
            "2026-04-04,WIRE CC-1002,10000.00,credit,STALE2\n"
        )
        first = Match.objects.get(transaction__bank_reference="STALE1")
        second = Match.objects.get(transaction__bank_reference="STALE2")
        self.assertEqual(self.client.post(f"/api/matches/{first.id}/approve/", HTTP_X_ORGANIZATION="northwind").status_code, 200)
        self.assertEqual(self.client.post(f"/api/matches/{second.id}/approve/", HTTP_X_ORGANIZATION="northwind").status_code, 409)
        second.line_item.refresh_from_db()
        self.assertEqual(second.line_item.amount_funded, Decimal("20000.00"))

    def test_approval_funds_once_and_repeat_returns_409(self):
        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-03,WIRE CC-1001,20000.00,credit,APPROVE1\n"
        )
        match = Match.objects.get(transaction__bank_reference="APPROVE1")
        approve_url = f"/api/matches/{match.id}/approve/"
        first = self.client.post(approve_url, HTTP_X_ORGANIZATION="northwind")
        second = self.client.post(approve_url, HTTP_X_ORGANIZATION="northwind")
        match.line_item.refresh_from_db()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(match.line_item.amount_funded, Decimal("20000.00"))
        self.assertEqual(match.line_item.status, LineItem.Status.PARTIAL)

    def test_cross_organization_listing_and_approval_return_404(self):
        self.upload(
            "date,description,amount,type,reference\n"
            "2026-04-03,WIRE CC-1001,20000.00,credit,PRIVATE1\n"
        )
        match = Match.objects.get(transaction__bank_reference="PRIVATE1")
        self.assertEqual(self.client.get("/api/transactions/", HTTP_X_ORGANIZATION="bluebird").data, [])
        response = self.client.post(f"/api/matches/{match.id}/approve/", HTTP_X_ORGANIZATION="bluebird")
        self.assertEqual(response.status_code, 404)

    def test_organization_header_errors(self):
        missing = self.client.get("/api/line-items/")
        unknown = self.client.get("/api/line-items/", HTTP_X_ORGANIZATION="no-such-org")
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(unknown.status_code, 404)

    def test_cors_preflight_allows_organization_header(self):
        response = self.client.options(
            "/api/transactions/",
            HTTP_ORIGIN="http://127.0.0.1:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-organization",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://127.0.0.1:5173")
        self.assertIn("x-organization", response["Access-Control-Allow-Headers"])

    def test_seed_demo_is_idempotent(self):
        before = (Organization.objects.count(), LineItem.objects.count())
        call_command("seed_demo", verbosity=0)
        after = (Organization.objects.count(), LineItem.objects.count())
        self.assertEqual(before, (2, 7))
        self.assertEqual(after, before)

    def test_bank_reference_can_repeat_in_another_organization(self):
        csv_text = (
            "date,description,amount,type,reference\n"
            "2026-04-03,UNKNOWN WIRE,10.00,credit,SAME-REF\n"
        )
        self.upload(csv_text, organization="northwind")
        self.upload(csv_text, organization="bluebird")
        self.assertEqual(BankTransaction.objects.filter(bank_reference="SAME-REF").count(), 2)
