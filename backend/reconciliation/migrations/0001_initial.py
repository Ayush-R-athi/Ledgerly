import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("name", models.CharField(max_length=160)),
            ],
        ),
        migrations.CreateModel(
            name="Investor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="investors", to="reconciliation.organization")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="CapitalCall",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField()),
                ("call_date", models.DateField()),
                ("due_date", models.DateField()),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="capital_calls", to="reconciliation.organization")),
            ],
            options={"ordering": ["number"]},
        ),
        migrations.CreateModel(
            name="LineItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("expected_reference", models.CharField(max_length=80)),
                ("amount_called", models.DecimalField(decimal_places=2, max_digits=14)),
                ("amount_funded", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.CharField(choices=[("open", "Open"), ("partially_funded", "Partially funded"), ("funded", "Funded")], default="open", max_length=24)),
                ("capital_call", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="line_items", to="reconciliation.capitalcall")),
                ("investor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="line_items", to="reconciliation.investor")),
            ],
        ),
        migrations.CreateModel(
            name="BankTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("description", models.TextField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("kind", models.CharField(choices=[("credit", "Credit"), ("debit", "Debit")], max_length=8)),
                ("bank_reference", models.CharField(max_length=120)),
                ("status", models.CharField(choices=[("suggested", "Suggested"), ("needs_review", "Needs review"), ("reconciled", "Reconciled"), ("ignored", "Ignored")], max_length=24)),
                ("review_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transactions", to="reconciliation.organization")),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.CreateModel(
            name="Match",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("proposed", "Proposed"), ("approved", "Approved"), ("rejected", "Rejected")], default="proposed", max_length=12)),
                ("reason", models.TextField()),
                ("line_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="matches", to="reconciliation.lineitem")),
                ("transaction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matches", to="reconciliation.banktransaction")),
            ],
        ),
        migrations.AddConstraint("investor", models.UniqueConstraint(fields=("organization", "name"), name="unique_investor_per_org")),
        migrations.AddConstraint("capitalcall", models.UniqueConstraint(fields=("organization", "number"), name="unique_call_number_per_org")),
        migrations.AddConstraint("lineitem", models.UniqueConstraint(fields=("capital_call", "investor"), name="unique_line_item_in_call")),
        migrations.AddConstraint("lineitem", models.CheckConstraint(condition=models.Q(("amount_funded__gte", 0)), name="funded_nonnegative")),
        migrations.AddConstraint("lineitem", models.CheckConstraint(condition=models.Q(("amount_funded__lte", models.F("amount_called"))), name="funded_not_over_called")),
        migrations.AddConstraint("banktransaction", models.UniqueConstraint(fields=("organization", "bank_reference"), name="unique_bank_reference_per_org")),
        migrations.AddConstraint("match", models.UniqueConstraint(fields=("transaction", "line_item"), name="unique_match_per_transaction")),
    ]
