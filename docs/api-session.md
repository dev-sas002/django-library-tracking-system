# Captured API session

Everything below was recorded on 2026-11-08 against the Compose stack, brought up
from a clean checkout with `docker compose up --build` on this repo's ports (API on
`8210`). The data is what `manage.py seed_library` writes on first boot. Nothing was
inserted by hand. Responses are verbatim; where a response was long, only the fields
that matter are shown and the trim is marked `# trimmed`. Worker logs have their MIME
headers (Date, Message-ID and encoding), task ids and timings shortened.

---

## 1. One command brings the stack up, migrated and seeded

```console
$ docker compose up --build -d
$ docker compose ps
SERVICE   STATUS                    PORTS
beat      Up 10 seconds (healthy)   8000/tcp
db        Up 21 seconds (healthy)   0.0.0.0:8211->5432/tcp
redis     Up 21 seconds (healthy)   0.0.0.0:8212->6379/tcp
web       Up 16 seconds (healthy)   0.0.0.0:8210->8000/tcp
worker    Up 10 seconds (healthy)   8000/tcp

$ docker compose logs web | grep -E 'entrypoint|Seeded|superuser'
[entrypoint] applying migrations
[entrypoint] seeding demo data (idempotent)
Created superuser "librarian" with the default demo password. Set LIBRARIAN_USERNAME / LIBRARIAN_PASSWORD before using this anywhere real.
Seeded 5 authors, 10 books, 5 members, 10 loans (10 new, 3 currently overdue).
```

The seed runs on every boot and is idempotent. After the web container was
recreated, the same command logged:

```console
Seeded 5 authors, 10 books, 5 members, 10 loans (0 new, 3 currently overdue).
```

The seed deliberately produces all three loan states, so `status`, the overdue
job and the extension rules all have something real to act on from the first boot.
Loan ids follow the seed order: `3` is active, `6` is overdue, and `10` is returned.

## 2. Health check

This endpoint is unauthenticated by design. The container `HEALTHCHECK` calls it,
and it checks the database connection, not just that the process is alive.

```console
$ curl -s http://localhost:8210/health/
{"status":"ok","database":"ok"}
```

## 3. Browsing the catalogue: anonymous reads, paginated

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

Listing books issues **two** queries, one `COUNT` and one joined `SELECT`, no matter
how many authors appear on the page. `test_list_does_not_issue_a_query_per_author`
asserts this.

## 4. Writes require authentication

```console
$ curl -s -w '\nHTTP %{http_code}\n' -X POST http://localhost:8210/api/books/1/loan/ -d 'member_id=1'
{"detail":"Authentication credentials were not provided."}
HTTP 403
```

## 5. Loaning a copy

The stock decrement happens in the same transaction that creates the loan, and a
confirmation is queued to Celery.

```console
$ curl -s -u librarian:librarian http://localhost:8210/api/books/1/        # trimmed
{'title': 'The Dispossessed', 'available_copies': 3}

$ curl -s -u librarian:librarian -X POST http://localhost:8210/api/books/1/loan/ \
      -H 'Content-Type: application/json' -d '{"member_id": 2}'
{"status":"Book loaned successfully.","loan_id":11}
HTTP 201

$ curl -s -u librarian:librarian http://localhost:8210/api/books/1/        # trimmed
{'title': 'The Dispossessed', 'available_copies': 2}
```

## 6. The worker delivers the confirmation

`EMAIL_BACKEND` defaults to Django's console backend, so the message shows up in the
worker log and no SMTP server is needed.

```console
$ docker compose logs worker --since 30s                                   # trimmed
[2026-11-08 02:18:58,934: INFO/MainProcess] Task library.tasks.send_loan_notification[7f800f07-...] received
[2026-11-08 02:18:58,960: WARNING/ForkPoolWorker-8] Content-Type: text/plain; charset="utf-8"
Subject: Book Loaned Successfully
From: admin@library.com
To: bo@example.com

Hello bo,

You have successfully loaned "The Dispossessed".
Please return it by 2026-11-22.
[2026-11-08 02:18:58,963: INFO/ForkPoolWorker-8] Task library.tasks.send_loan_notification[7f800f07-...] succeeded in 0.028s: 1
```

## 7. Extending a loan: the state machine, enforced

```console
$ curl -s -u librarian:librarian -X POST http://localhost:8210/api/loans/3/extend_due_date/ \
      -H 'Content-Type: application/json' -d '{"additional_days": 7}'          # trimmed
{'id': 3, 'due_date': '2026-11-18', 'status': 'active', 'is_overdue': False}
```

Every rejection carries a human-readable `error` and a stable machine `code`:

```console
$ ... /api/loans/6/extend_due_date/   -d '{"additional_days": 7}'         # overdue loan
{"error":"Cannot extend an overdue loan.","code":"loan_overdue"}
HTTP 400

$ ... /api/loans/10/extend_due_date/  -d '{"additional_days": 7}'         # returned loan
{"error":"Loan has already been returned.","code":"loan_already_returned"}
HTTP 400

$ ... /api/loans/3/extend_due_date/   -d '{"additional_days": -3}'
{"error":"additional_days must be between 1 and 365.","code":"invalid_extension"}
HTTP 400

$ ... /api/loans/3/extend_due_date/   -d '{"additional_days": 3000000}'   # was a 500
{"error":"additional_days must be between 1 and 365.","code":"invalid_extension"}
HTTP 400

$ ... /api/loans/3/extend_due_date/   -d '{"additional_days": 2.7}'       # was silently 2
{"error":"additional_days must be an integer.","code":"additional_days_not_an_integer"}
HTTP 400

$ ... /api/loans/3/extend_due_date/   -d '{}'
{"error":"additional_days is required.","code":"additional_days_required"}
HTTP 400
```

## 8. The rest of the error contract

```console
$ ... POST /api/books/5/loan/          -d '{"member_id": 1}'      # Excession, 0 copies left
{"error":"No available copies.","code":"book_unavailable"}
HTTP 400

$ ... POST /api/books/1/loan/          -d '{"member_id": 9999}'
{"error":"Member does not exist.","code":"member_not_found"}
HTTP 400

$ ... POST /api/books/5/return_book/   -d '{"member_id": 1}'      # member holds no copy
{"error":"Active loan does not exist.","code":"no_active_loan"}
HTTP 400

$ ... POST /api/members/               -d '{"user_id": 1}'        # amara already has one
{"user_id":["This user already has a member profile."]}
HTTP 400
```

## 9. `/api/loans/`: the same rules as the book action

`POST /api/loans/` goes through the same locked `loan_book` call as
`POST /api/books/{id}/loan/` and queues the same confirmation. You can choose a
`due_date`, but it must fall between today and a year from now.

```console
$ ... POST /api/loans/  -d '{"book_id": 7, "member_id": 4, "due_date": "2001-01-01"}'
{"error":"due_date must be between 2026-11-08 and 2027-11-08.","code":"invalid_due_date"}
HTTP 400

$ ... POST /api/loans/  -d '{"book_id": 7, "member_id": 4}'                      # trimmed
{'id': 12, 'book': {'title': 'Ancillary Sword', 'available_copies': 0}, 'member': 'dalia', 'due_date': '2026-11-22', 'status': 'active'}
HTTP 201
```

The generic update routes are switched off, so they can no longer close a loan
without restocking it. Closing one specific loan has its own action:

```console
$ ... PATCH /api/loans/12/  -d '{"is_returned": true}'
{"detail":"Method \"PATCH\" not allowed."}
HTTP 405

$ ... POST /api/loans/12/return/                                                 # trimmed
{'id': 12, 'status': 'returned', 'return_date': '2026-11-08', 'is_returned': True}
HTTP 200

$ ... POST /api/loans/12/return/
{"error":"Loan has already been returned.","code":"loan_already_returned"}
HTTP 400

$ ... GET /api/books/7/                                                          # trimmed
{'title': 'Ancillary Sword', 'available_copies': 1}
```

## 10. Returning by book and member puts the copy back on the shelf

```console
$ ... GET /api/books/5/                                                          # trimmed
{'title': 'Excession', 'available_copies': 0}

$ curl -s -w '\nHTTP %{http_code}\n' -u librarian:librarian \
      -X POST http://localhost:8210/api/books/5/return_book/ \
      -H 'Content-Type: application/json' -d '{"member_id": 3}'
{"status":"Book returned successfully."}
HTTP 200

$ ... GET /api/books/5/                                                          # trimmed
{'title': 'Excession', 'available_copies': 1}
```

## 11. The nightly overdue job, actually running

Celery beat schedules `check_overdue_loans` for 08:00 UTC every day. Here it is
run on demand against the same worker:

```console
$ docker compose exec web python -c "
from library_system.celery import app
r = app.send_task('library.tasks.check_overdue_loans')
print('queued task id:', r.id)
print('reminders sent:', r.get(timeout=30))"
queued task id: e7dcec2a-804c-4102-8144-ccab12676728
reminders sent: 2
```

```console
$ docker compose logs worker --since 20s                                   # trimmed
[2026-11-08 02:19:07,337: INFO/MainProcess] Task library.tasks.check_overdue_loans[e7dcec2a-...] received
[2026-11-08 02:19:07,346: WARNING/ForkPoolWorker-8] Content-Type: text/plain; charset="utf-8"
Subject: Overdue Book Loan
From: admin@library.com
To: bo@example.com

Hello bo,

"Ancillary Justice" was due on 2026-10-28 (11 day(s) ago). Please return it.
-------------------------------------------------------------------------------
Content-Type: text/plain; charset="utf-8"
Subject: Overdue Book Loan
From: admin@library.com
To: amara@example.com

Hello amara,

"Stiff" was due on 2026-11-04 (4 day(s) ago). Please return it.
-------------------------------------------------------------------------------
[2026-11-08 02:19:07,347: INFO/ForkPoolWorker-8] check_overdue_loans: sent 2 reminder(s)
[2026-11-08 02:19:07,347: INFO/ForkPoolWorker-8] Task library.tasks.check_overdue_loans[e7dcec2a-...] succeeded in 0.010s: 2
```

Two things are worth noticing:

- The seed created **three** overdue loans, but only **two** reminders went out. The
  third was the Excession loan returned in step 10, and a returned loan is no longer
  overdue. The job reads the current state, not a stored flag.
- Reminders go out **oldest debt first** (11 days late before 4 days late), because
  `LoanQuerySet.overdue()` orders by `due_date`.

The job can be replayed for another date. Through the broker, `as_of` arrives as an
ISO string, which used to raise a `TypeError` on the worker:

```console
$ docker compose exec web python -c "
from library_system.celery import app
print('reminders sent:', app.send_task('library.tasks.check_overdue_loans',
      kwargs={'as_of': '2026-11-28'}).get(timeout=30))"
reminders sent: 8

[2026-11-08 02:19:09,996: INFO/ForkPoolWorker-8] check_overdue_loans: sent 8 reminder(s)
```

## 12. Tests and lint

The suite runs on Django's own test runner with SQLite, inside `python:3.12-slim`
with no network:

```console
$ DB_ENGINE=django.db.backends.sqlite3 DEBUG=1 python manage.py test
Found 156 test(s).
System check identified no issues (0 silenced).
...
Ran 156 tests in 50.211s

OK

$ ruff check . && ruff format --check .
All checks passed!
41 files already formatted

$ python manage.py makemigrations --check --dry-run
No changes detected
```
