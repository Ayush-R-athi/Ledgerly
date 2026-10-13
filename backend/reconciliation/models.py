from django.db import models


class Organization(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=160)

    def __str__(self):
        return self.name


class Investor(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="investors")
    name = models.CharField(max_length=200)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="unique_investor_per_org")]
        ordering = ["name"]


class CapitalCall(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="capital_calls")
    number = models.PositiveIntegerField()
    call_date = models.DateField()
    due_date = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "number"], name="unique_call_number_per_org")]
        ordering = ["number"]


class LineItem(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PARTIAL = "partially_funded", "Partially funded"
        FUNDED = "funded", "Funded"

    capital_call = models.ForeignKey(CapitalCall, on_delete=models.CASCADE, related_name="line_items")
    investor = models.ForeignKey(Investor, on_delete=models.PROTECT, related_name="line_items")
    expected_reference = models.CharField(max_length=80)
    amount_called = models.DecimalField(max_digits=14, decimal_places=2)
    amount_funded = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["capital_call", "investor"], name="unique_line_item_in_call"),
            models.CheckConstraint(condition=models.Q(amount_funded__gte=0), name="funded_nonnegative"),
            models.CheckConstraint(condition=models.Q(amount_funded__lte=models.F("amount_called")), name="funded_not_over_called"),
        ]

    @property
    def remaining(self):
        return self.amount_called - self.amount_funded


class BankTransaction(models.Model):
    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        REVIEW = "needs_review", "Needs review"
        RECONCILED = "reconciled", "Reconciled"
        IGNORED = "ignored", "Ignored"

    class Kind(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="transactions")
    date = models.DateField()
    description = models.TextField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    bank_reference = models.CharField(max_length=120)
    status = models.CharField(max_length=24, choices=Status.choices)
    review_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "bank_reference"], name="unique_bank_reference_per_org")]
        ordering = ["-date", "-id"]


class Match(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    transaction = models.ForeignKey(BankTransaction, on_delete=models.CASCADE, related_name="matches")
    line_item = models.ForeignKey(LineItem, on_delete=models.PROTECT, related_name="matches")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROPOSED)
    reason = models.TextField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["transaction", "line_item"], name="unique_match_per_transaction")]
