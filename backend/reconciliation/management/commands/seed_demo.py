from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from reconciliation.models import CapitalCall, Investor, LineItem, Organization


class Command(BaseCommand):
    help = "Create the repeatable Ledgerly demonstration organizations and capital calls."

    def handle(self, *args, **options):
        northwind, _ = Organization.objects.update_or_create(
            slug="northwind", defaults={"name": "Northwind Ventures"}
        )
        bluebird, _ = Organization.objects.update_or_create(
            slug="bluebird", defaults={"name": "Bluebird Capital"}
        )

        call_one, _ = CapitalCall.objects.update_or_create(
            organization=northwind, number=1,
            defaults={"call_date": date(2026, 3, 25), "due_date": date(2026, 4, 10)},
        )
        call_two, _ = CapitalCall.objects.update_or_create(
            organization=northwind, number=2,
            defaults={"call_date": date(2026, 4, 1), "due_date": date(2026, 4, 20)},
        )
        bluebird_call, _ = CapitalCall.objects.update_or_create(
            organization=bluebird, number=1,
            defaults={"call_date": date(2026, 4, 1), "due_date": date(2026, 4, 15)},
        )

        rows = [
            (call_one, northwind, "Haller Capital LLC", "CC-1001", "27500.00"),
            (call_one, northwind, "Rahul Shah Trust", "CC-1002", "25000.00"),
            (call_one, northwind, "Patel Family Trust", "CC-1003", "12500.00"),
            (call_one, northwind, "Meridian Partners LP", "CC-1004", "15000.00"),
            (call_one, northwind, "Oakridge Holdings LLC", "CC-1005", "15000.00"),
            (call_two, northwind, "Oakridge Holdings LLC", "CC-1006", "15000.00"),
            (bluebird_call, bluebird, "Cedar Grove Fund LP", "CC-2001", "40000.00"),
        ]
        for capital_call, organization, investor_name, reference, amount in rows:
            investor, _ = Investor.objects.get_or_create(
                organization=organization, name=investor_name
            )
            LineItem.objects.get_or_create(
                capital_call=capital_call,
                investor=investor,
                defaults={"expected_reference": reference, "amount_called": Decimal(amount)},
            )

        self.stdout.write(self.style.SUCCESS("Demo organizations and line items are ready."))
