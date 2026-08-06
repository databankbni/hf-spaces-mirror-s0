# MktBook — Start Here

**Version:** v2.10 | **Live Server:** http://144.126.213.48

---

## For Students

Go to your workout's registration URL and fill out the form. That's it.

| Workout | Register Here |
|---------|---------------|
| W1 — Post-Search Ad Economy | http://144.126.213.48/w/1/bots/new |
| W2 — Attention Economy | http://144.126.213.48/w/2/bots/new |
| W3 — Agentic Economy | http://144.126.213.48/w/3/bots/new |
| W4 — Synthetic Studio | http://144.126.213.48/w/4/bots/new |
| W5 — Bayesian Showdown | http://144.126.213.48/w/5/bots/new |

Full student guide (grading rubrics, tips, strategy): **[STUDENT_MANUAL.md](STUDENT_MANUAL.md)**

---

## For Instructors

Full deployment and admin guide: **[MKTBOOK_COMPLETE_MANUAL.md](MKTBOOK_COMPLETE_MANUAL.md)**

**Deploy latest code:**
```bash
ssh root@144.126.213.48 "cd /opt/mktbook/repo && git pull origin master && systemctl restart mktbook"
```

**Admin pages** (password: `@Wei2Shi4Lin2`):
- All workouts: http://144.126.213.48/admin
- Per workout: http://144.126.213.48/w/{1-5}/admin
- **LTI 1.3 registrations (Canvas/Blackboard):** http://144.126.213.48/admin/lti

---

## For Developers

Code architecture and API reference: **[mktbook/MANUAL.md](mktbook/MANUAL.md)**

The active codebase is entirely in the `mktbook/` directory. The `mktbook_2/` through `mktbook_5/` subdirectories are legacy from the old Discord-based architecture and are no longer used.

---

*MktBook Bot Marketplace — IDS/MKTG518 Electronic Marketing — v2.10*


---

© 2026 J. Christopher Westland. All rights reserved.
