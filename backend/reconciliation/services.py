import csv
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import F

from .models import BankTransaction, LineItem, Match


def normalize_reference(value):
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def normalize_name(value):
    name = re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()
    name = re.sub(r"\s+", " ", name)
    return re.sub(r"\s+(LLC|LP|LTD|INC)$", "", name).strip()


def name_is_found(investor_name, description):
    name = normalize_name(investor_name)
    text = normalize_name(description)
    return bool(name) and f" {name} " in f" {text} "


def suggest_matches(bank_transaction):
    eligible = list(
        LineItem.objects.select_related("investor", "capital_call")
        .filter(capital_call__organization=bank_transaction.organization,
                capital_call__call_date__lte=bank_transaction.date,
                amount_funded__lt=F("amount_called"))
        .order_by("id")
    )
    description_ref = normalize_reference(bank_transaction.description)
    bank_ref = normalize_reference(bank_transaction.bank_reference)
    reference_hits = [
        item for item in eligible
        if normalize_reference(item.expected_reference) in description_ref
        or normalize_reference(item.expected_reference) in bank_ref
    ]

    if len(reference_hits) == 1:
        item = reference_hits[0]
        if bank_transaction.amount > item.remaining:
            bank_transaction.status = BankTransaction.Status.REVIEW
            bank_transaction.review_reason = (
                f"Reference {item.expected_reference} found, but payment {bank_transaction.amount:.2f} "
                f"exceeds remaining amount {item.remaining:.2f}."
            )
            bank_transaction.save(update_fields=["status", "review_reason"])
            return
        Match.objects.create(
            transaction=bank_transaction, line_item=item,
            reason=f"Reference {item.expected_reference} found; payment {bank_transaction.amount:.2f} "
                   f"is within remaining amount {item.remaining:.2f}.",
        )
        bank_transaction.status = BankTransaction.Status.SUGGESTED
        bank_transaction.save(update_fields=["status"])
        return

    if len(reference_hits) > 1:
        for item in reference_hits:
            Match.objects.create(
                transaction=bank_transaction, line_item=item,
                reason=f"Reference {item.expected_reference} found; multiple eligible reference matches need review.",
            )
        bank_transaction.status = BankTransaction.Status.REVIEW
        bank_transaction.review_reason = f"{len(reference_hits)} eligible capital call references were found."
        bank_transaction.save(update_fields=["status", "review_reason"])
        return

    name_hits = [
        item for item in eligible
        if item.remaining == bank_transaction.amount
        and name_is_found(item.investor.name, bank_transaction.description)
    ]
    if len(name_hits) == 1:
        item = name_hits[0]
        Match.objects.create(
            transaction=bank_transaction, line_item=item,
            reason=f"Investor name {item.investor.name} and exact remaining amount {item.remaining:.2f} match.",
        )
        bank_transaction.status = BankTransaction.Status.SUGGESTED
        bank_transaction.save(update_fields=["status"])
    elif len(name_hits) > 1:
        for item in name_hits:
            Match.objects.create(
                transaction=bank_transaction, line_item=item,
                reason=f"Investor name found and amount equals remaining {item.remaining:.2f}; multiple candidates need review.",
            )
        bank_transaction.status = BankTransaction.Status.REVIEW
        bank_transaction.review_reason = f"{len(name_hits)} investors match the name and amount; choose the correct line item."
        bank_transaction.save(update_fields=["status", "review_reason"])
    else:
        bank_transaction.status = BankTransaction.Status.REVIEW
        bank_transaction.review_reason = "No eligible line item matched the reference, investor name, and payment amount."
        bank_transaction.save(update_fields=["status", "review_reason"])


def parse_csv_amount(raw):
    value = raw.replace(",", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
        raise ValueError("amount must be a valid number")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("amount must be a valid number") from exc
    if not amount.is_finite():
        raise ValueError("amount must be a finite number")
    if amount == 0:
        raise ValueError("amount cannot be zero")
    if amount.as_tuple().exponent < -2:
        raise ValueError("amount can have at most two decimal places")
    return amount


def import_statement(file_obj, organization):
    text = file_obj.read().decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    required = {"date", "description", "amount", "type", "reference"}
    reader.fieldnames = [(column or "").strip() for column in (reader.fieldnames or [])]
    columns = set(reader.fieldnames)
    missing = sorted(required - columns)
    if missing:
        return {"imported": 0, "duplicates": 0, "errors": [{
            "line": 1, "message": f"Missing required column(s): {', '.join(missing)}. No rows were imported."
        }], "file_rejected": True}, 400

    imported = duplicates = 0
    errors = []
    seen_references = set()
    with transaction.atomic():
        for line_number, raw_row in enumerate(reader, start=2):
            row = {(key or "").strip(): (value or "").strip() for key, value in raw_row.items()}
            try:
                if None in raw_row:
                    raise ValueError("row has more values than the header")
                if any(not row.get(field) for field in required):
                    raise ValueError("date, description, amount, type, and reference are required")
                try:
                    parsed_date = date.fromisoformat(row["date"])
                except ValueError as exc:
                    raise ValueError("date must be a real date in YYYY-MM-DD format") from exc
                if parsed_date.isoformat() != row["date"]:
                    raise ValueError("date must use YYYY-MM-DD format")
                kind = row["type"].lower()
                if kind not in {"credit", "debit"}:
                    raise ValueError("type must be credit or debit")
                amount = parse_csv_amount(row["amount"])
                if kind == "credit" and amount < 0:
                    raise ValueError("credit amounts must be positive")
                if kind == "debit" and amount > 0:
                    raise ValueError("debit amounts must be negative")
                reference = row["reference"]
                if reference in seen_references or BankTransaction.objects.filter(
                    organization=organization, bank_reference=reference
                ).exists():
                    duplicates += 1
                    seen_references.add(reference)
                    continue
                bank_transaction = BankTransaction.objects.create(
                    organization=organization, date=parsed_date, description=row["description"],
                    amount=amount, kind=kind, bank_reference=reference,
                    status=BankTransaction.Status.IGNORED if kind == "debit" else BankTransaction.Status.REVIEW,
                )
                seen_references.add(reference)
                imported += 1
                if kind == "credit":
                    suggest_matches(bank_transaction)
            except (ValueError, TypeError) as exc:
                errors.append({"line": line_number, "message": str(exc)})
    return {"imported": imported, "duplicates": duplicates, "errors": errors, "file_rejected": False}, 200


@transaction.atomic
def approve_match(match_id, organization):
    match = Match.objects.select_for_update().select_related("transaction").filter(
        pk=match_id, transaction__organization=organization
    ).first()
    if match is None:
        return None, "not_found"
    if match.status != Match.Status.PROPOSED or match.transaction.status not in {
        BankTransaction.Status.SUGGESTED, BankTransaction.Status.REVIEW
    }:
        return None, "conflict"
    line_item = LineItem.objects.select_for_update().get(pk=match.line_item_id)
    if match.transaction.amount > line_item.remaining:
        return None, "amount_conflict"
    line_item.amount_funded += match.transaction.amount
    line_item.status = (
        LineItem.Status.FUNDED if line_item.amount_funded == line_item.amount_called
        else LineItem.Status.PARTIAL
    )
    line_item.save(update_fields=["amount_funded", "status"])
    match.status = Match.Status.APPROVED
    match.save(update_fields=["status"])
    Match.objects.filter(transaction=match.transaction).exclude(pk=match.pk).update(status=Match.Status.REJECTED)
    match.transaction.status = BankTransaction.Status.RECONCILED
    match.transaction.review_reason = ""
    match.transaction.save(update_fields=["status", "review_reason"])
    return match, None
