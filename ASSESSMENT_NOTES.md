# Ledgerly — assessment reference notes

## App and scope

**Ledgerly** is a one-page capital call reconciliation app for a general partner. A GP selects an organization, uploads a bank statement CSV, reviews one-time matching suggestions, and approves, rejects, or ignores them. Approval increases funded capital without allowing funding above the call amount.

The app implements the required assessment scope. Airtable, authentication, background jobs, and money movement are intentionally not included because they are optional or out of scope.

## Requirements

- Django and Django REST Framework API, PostgreSQL database, React SPA built with Vite.
- Idempotent `seed_demo` management command creates both organizations and all seven specified line items.
- CSV import is a UI action; malformed file headers reject the file, invalid rows are skipped with line numbers, and duplicates are scoped by organization.
- Credits are matched from normalized references first, then exact remaining amount plus normalized investor name. Debits are imported as ignored.
- Match and review reasons are persisted. Approval uses a database transaction and row locks, rechecks remaining amount, and rejects the other proposals.
- Every API endpoint requires `X-Organization`; records from another tenant are hidden with `404`.
- The UI has organization switching, CSV upload summary, transactions, actions, line item balances, loading/empty/error states, and refreshes after actions.

## Setup from a fresh clone

Prerequisites: Python 3.11+, Node.js 22.12+, npm, and Docker Desktop (or a local PostgreSQL 16 server).

1. Copy `.env.example` to `backend/.env` and change `DJANGO_SECRET_KEY` for a non-local deployment.
2. From the repository root, start PostgreSQL with `docker compose up -d db`.
3. In a terminal:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python manage.py migrate
   python manage.py seed_demo
   python manage.py runserver
   ```

4. In a second terminal:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

5. Open the Vite URL printed in the frontend terminal. Select an organization and import `sample_bank_statement (1).csv` from the repository root.

For a local run without PostgreSQL, omit `DATABASE_URL` from `backend/.env`; Django uses SQLite as a development convenience. PostgreSQL is the required assessment database and is configured by the supplied example.

## Tests

Run the backend test suite from `backend/` with this single command:

```powershell
python manage.py test
```

The suite covers missing columns/no writes, Decimal parsing and invalid rows, duplicates, normalized reference and name matching, ambiguous candidates, overpayments, approval and double approval, and organization isolation.

## Data model

- `Organization` owns the tenant boundary.
- `Investor` is a legal entity within one organization.
- `CapitalCall` belongs to an organization and holds call/due dates.
- `LineItem` joins one call and investor, stores the expected wire reference, called/funded decimals, and derived remaining amount.
- `BankTransaction` stores the imported bank row, credit/debit kind, status, and review reason. Bank references are unique per organization.
- `Match` connects one transaction and line item, and stores its status and explanation.

## API endpoints

All endpoints use the `X-Organization: northwind` or `X-Organization: bluebird` header.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/import/` | Multipart CSV upload; file field is `file`; returns imported, duplicates, and row errors |
| `GET` | `/api/transactions/` | Organization-scoped transactions newest first, including matches and reasons |
| `GET` | `/api/line-items/` | Organization-scoped called, funded, remaining, and status values |
| `POST` | `/api/matches/{id}/approve/` | Approve proposed match and fund its line item |
| `POST` | `/api/matches/{id}/reject/` | Reject a proposed match |
| `POST` | `/api/transactions/{id}/ignore/` | Ignore a suggested or review transaction and reject its matches |

Missing organization headers return `400`; unknown organizations and cross-tenant records return `404`; invalid or repeated actions return `409`.

## Assumptions and trade-offs

- Bank references are unique per organization and compared after trimming, preserving case because the spec does not define bank-reference normalization for deduplication.
- CSV amounts accept an optional sign, thousands separators, and up to two decimal places; zero, malformed values, and credit/debit sign mismatches are rejected row by row.
- The requested “letters and digits” normalization is applied to ASCII A–Z and 0–9. The supplied data uses ASCII names and references.
- Ambiguous reference/name matches are all proposed for GP review. An overpayment for one unique reference creates no match and needs review.
- A partial reference payment is suggested when it does not exceed remaining. Name-based suggestions require an exact remaining-amount match.
- `remaining` is calculated as called minus funded; the database also prevents funding above the amount called.
- SQLite is available only as a local convenience; the assessment setup uses PostgreSQL.

## Next steps

- Add the optional Airtable sync behind a small client interface and environment variables.
- Add pagination and import limits based on production traffic.
- Add authentication and authorization if the product scope includes real users.
- Record a short walkthrough and provide deployment URLs if deployment time permits.

## Five-minute recording outline

1. Run `python manage.py seed_demo`, then start the API and React page.
2. Show the organization switcher and select Northwind Ventures.
3. Upload the sample CSV; show the imported count, duplicate count, and row errors area.
4. Point out the reference and name suggestions, plus the unmatched and ambiguous `needs_review` rows.
5. Approve a suggested match and show the funded and remaining amounts refresh.
6. Switch to Bluebird Capital to show its isolated line items and transaction list.
7. Briefly tour the Django models/services, API endpoints, and React page.

## Student integrity declaration

The assessment requires the student to include the following statement only when it is true for their own submission:

> I completed this assessment without using AI assistance.
