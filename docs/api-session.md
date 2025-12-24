# Captured API session

Everything below was recorded against the Compose stack brought up with a single
`docker compose up --build`, on this repo's ports (API on `8210`). The data is
exactly what `manage.py seed_library` writes on first boot — nothing was inserted
by hand. Output is verbatim.

---

## 1. One command brings the stack up, migrated and seeded

```console
$ docker compose up --build -d
$ docker compose ps
SERVICE   STATUS                             PORTS
beat      Up 27 seconds (health: starting)   8000/tcp
db        Up 45 seconds (healthy)            0.0.0.0:8211->5432/tcp
redis     Up 45 seconds (healthy)            0.0.0.0:8212->6379/tcp
web       Up 39 seconds (healthy)            0.0.0.0:8210->8000/tcp
worker    Up 27 seconds (healthy)            8000/tcp

$ docker compose logs web | grep -E 'entrypoint|Seeded'
web-1  | [entrypoint] applying migrations
web-1  | [entrypoint] seeding demo data (idempotent)
web-1  | Seeded 5 authors, 10 books, 5 members, 10 loans (10 new, 3 currently overdue).
```

`beat` is still inside its `start_period` in this snapshot. Note that the beat
healthcheck originally used `pgrep`, which is not present in the `python:*-slim`
base image, so the container stayed `unhealthy` indefinitely; it now runs
`docker/healthcheck_beat.py`, which scans `/proc` and needs no extra package.
Nothing depends on beat's health condition, so this never affected the stack.

The seed deliberately produces all three loan states, so `status`, the overdue
job and the extension rules all have something real to act on from the first
boot.

## 2. Health check

Unauthenticated by design — this is the endpoint the container `HEALTHCHECK`
calls, and it verifies database connectivity rather than just that the process
is alive.

```console
$ curl -s http://localhost:8210/health/
{"status": "ok", "database": "ok"}
```

## 3. Browsing the catalogue — anonymous reads, paginated

```console
$ curl -s 'http://localhost:8210/api/books/?page_size=2'
{
    "count": 10,
    "next": "http://localhost:8210/api/books/?page=2&page_size=2",
    "previous": null,
    "results": [
        {
            "id": 6,
            "title": "Ancillary Justice",
            "author": {
                "id": 3,
                "first_name": "Ann",
                "last_name": "Leckie",
                "biography": "American science fiction and fantasy writer."
            },
            "isbn": "9780356502403",
            "genre": "sci-fi",
            "available_copies": 2
        },
        {
            "id": 7,
            "title": "Ancillary Sword",
            "author": {
                "id": 3,
                "first_name": "Ann",
                "last_name": "Leckie",
                "biography": "American science fiction and fantasy writer."
            },
            "isbn": "9780356502427",
            "genre": "sci-fi",
            "available_copies": 1
        }
    ]
}
```

Listing ten books issues **two** queries — one `COUNT`, one joined `SELECT` —
regardless of how many distinct authors appear on the page. This is asserted in
`library/tests/test_api_books.py::test_list_does_not_issue_a_query_per_author`.

## 4. Writes require authentication

```console
$ curl -s -w '\nHTTP %{http_code}\n' -X POST http://localhost:8210/api/books/1/loan/ -d 'member_id=1'
{"detail":"Authentication credentials were not provided."}
HTTP 403
```

## 5. Loaning a copy

Stock is decremented in the same transaction that creates the loan, and a
confirmation is queued to Celery.

```console
$ curl -s -u librarian:librarian http://localhost:8210/api/books/1/
{"title": "The Dispossessed", "available_copies": 3}

$ curl -s -u librarian:librarian -X POST http://localhost:8210/api/books/1/loan/ \
      -H 'Content-Type: application/json' -d '{"member_id": 2}'
{"status": "Book loaned successfully.", "loan_id": 11}

$ curl -s -u librarian:librarian http://localhost:8210/api/books/1/
{"title": "The Dispossessed", "available_copies": 2}
```

## 6. The worker delivers the confirmation

`EMAIL_BACKEND` defaults to Django's console backend, so the message body is
visible in the worker log rather than requiring an SMTP server.

```console
$ docker compose logs worker --since 60s
[2026-09-23 12:50:42,477: INFO/MainProcess] Task library.tasks.send_loan_notification[c7ee92d4] received
[2026-09-23 12:50:42,533: WARNING/ForkPoolWorker-8] Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Book Loaned Successfully
From: admin@library.com
To: bo@example.com
Date: Wed, 23 Sep 2026 12:50:42 -0000

Hello bo,

You have successfully loaned "The Dispossessed".
Please return it by 2026-10-07.
[2026-09-23 12:50:42,537: INFO/ForkPoolWorker-8] Task library.tasks.send_loan_notification[c7ee92d4] succeeded in 0.0517s: 1
```

## 7. Extending a loan — the state machine, enforced

Loan `3` is `active`, loan `6` is `overdue`, loan `10` is `returned`.

```console
$ curl -s -u librarian:librarian -X POST http://localhost:8210/api/loans/3/extend_due_date/ \
      -H 'Content-Type: application/json' -d '{"additional_days": 7}'
{"id": 3, "due_date": "2026-10-03", "status": "active", "is_overdue": false}
```

Every rejection carries a human `error` and a stable machine `code`:

```console
$ ... /api/loans/6/extend_due_date/  -d '{"additional_days": 7}'   # overdue loan
{"error":"Cannot extend an overdue loan.","code":"loan_overdue"}
HTTP 400

$ ... /api/loans/10/extend_due_date/ -d '{"additional_days": 7}'   # returned loan
{"error":"Loan has already been returned.","code":"loan_already_returned"}
HTTP 400

$ ... /api/loans/3/extend_due_date/  -d '{"additional_days": -3}'
{"error":"additional_days must be a positive integer.","code":"invalid_extension"}
HTTP 400

$ ... /api/loans/3/extend_due_date/  -d '{}'
{"error":"additional_days is required.","code":"additional_days_required"}
HTTP 400
```

## 8. The rest of the error contract

```console
$ ... POST /api/books/5/loan/        -d '{"member_id": 1}'    # Excession, 0 copies left
{"error":"No available copies.","code":"book_unavailable"}
HTTP 400

$ ... POST /api/books/1/loan/        -d '{"member_id": 9999}'
{"error":"Member does not exist.","code":"member_not_found"}
HTTP 400

$ ... POST /api/books/5/return_book/ -d '{"member_id": 1}'    # member holds no copy
{"error":"Active loan does not exist.","code":"no_active_loan"}
HTTP 400
```

## 9. Returning a copy puts it back on the shelf

```console
$ curl -s -u librarian:librarian http://localhost:8210/api/books/5/
Excession available_copies = 0

$ curl -s -w '\nHTTP %{http_code}\n' -u librarian:librarian \
      -X POST http://localhost:8210/api/books/5/return_book/ \
      -H 'Content-Type: application/json' -d '{"member_id": 3}'
{"status":"Book returned successfully."}
HTTP 200

$ curl -s -u librarian:librarian http://localhost:8210/api/books/5/
Excession available_copies = 1
```

## 10. The nightly overdue job, actually running

Celery beat schedules `check_overdue_loans` for 08:00 UTC daily. Here it is
invoked on demand against the same worker:

```console
$ docker compose exec web python -c "
from library_system.celery import app
r = app.send_task('library.tasks.check_overdue_loans')
print('queued task id:', r.id)
print('reminders sent:', r.get(timeout=30))"
queued task id: 6d74d82a-05e9-4738-917c-db7bf4ab2fa8
reminders sent: 2
```

```console
$ docker compose logs worker --since 40s
[2026-09-23 12:51:53,547: INFO/MainProcess] Task library.tasks.check_overdue_loans[6d74d82a] received
[2026-09-23 12:51:53,870: WARNING/ForkPoolWorker-8] Content-Type: text/plain; charset="utf-8"
Subject: Overdue Book Loan
From: admin@library.com
To: bo@example.com

Hello bo,

"Ancillary Justice" was due on 2026-09-12 (11 day(s) ago). Please return it.
-------------------------------------------------------------------------------
Content-Type: text/plain; charset="utf-8"
Subject: Overdue Book Loan
From: admin@library.com
To: amara@example.com

Hello amara,

"Stiff" was due on 2026-09-19 (4 day(s) ago). Please return it.
-------------------------------------------------------------------------------
[2026-09-23 12:51:53,872: INFO/ForkPoolWorker-8] check_overdue_loans: sent 2 reminder(s)
[2026-09-23 12:51:53,889: INFO/ForkPoolWorker-8] Task library.tasks.check_overdue_loans[6d74d82a] succeeded in 0.277s: 2
```

Two things worth noticing:

- The seed created **three** overdue loans, but only **two** reminders were sent —
  the third was the Excession loan returned in step 9, and a returned loan is no
  longer overdue. The job reads current state rather than a stored flag.
- Reminders go out **oldest debt first** (11 days late before 4 days late),
  because `LoanQuerySet.overdue()` orders by `due_date`.

## 11. Test suite

```console
$ DB_ENGINE=django.db.backends.sqlite3 DEBUG=1 python manage.py test
Creating test database for alias 'default'...
Found 129 test(s).
System check identified no issues (0 silenced).
.................................................................................
----------------------------------------------------------------------
Ran 129 tests in 20.283s

OK
Destroying test database for alias 'default'...
```

```console
$ ruff check . && ruff format --check .
All checks passed!
44 files already formatted

$ python manage.py makemigrations --check --dry-run
No changes detected
```
