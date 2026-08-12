# Review 001 — Admission review

Verdict at review time: **NOT SHIP**.

Independent architecture, official-Kronos and strict-PIT reviewers found P0/P1
issues before formal training: future missingness changed historical candidate
sets; latest-close and index membership availability lacked evidence; training
and inference receipts could overclaim source/checkpoint identity; six-cell PASS
was not derived from terminal receipts; online forecasts were labelled scoreable;
run publication and paper mutation were not atomic; historical model provenance
was mutable; and the UI overclaimed VPN-disconnect durability with `Linger=no`.

Repair status: code-level findings above were addressed in iteration 1 and are
covered by 24 server tests plus six frontend tests. Vendor membership revision
history remains an explicitly disclosed data limitation, not a claimed strict
fact. Linger remains an operational gate. A fresh independent review is required
after real training/evaluation and live E2E; this review does not grant SHIP.
