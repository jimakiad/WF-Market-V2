# Security audit — 2026-10-06

Scope: application source, all nine reachable Git commits, installed dependencies,
local authentication tests, and read-only checks of https://wf-market-v2.onrender.com.
Reviewed application commit: `3b71e4a`.

## Result

The initial audit identified two authentication issues and missing browser
hardening headers. Follow-up changes resolve these findings locally, and the
README now includes the live Render link and deployment/security behavior.
These changes are prepared for review and have not been committed, pushed, or
deployed. The live service still runs the previously reviewed commit until the
changes are published. Existing public Git history is preserved.

## Findings

### Resolved locally — copied sessions remained usable after logout

Location: `backend/app.py:215` and `backend/app.py:220`.

At the reviewed commit, authentication and the Warframe Market token were stored
in Flask's signed client cookie. Logout cleared the current browser's cookie,
but did not invalidate a copy on the server. A local test saved a test account's cookie,
logged out, and replayed the saved cookie: `/status` still returned `200`.
The logged-out original client received `401`.

This required possession of a valid cookie; it was not an unauthenticated login
bypass. A stolen session can remain usable after logout, subject to cookie and
upstream-token validity. The configured cookie signature lifetime is 12 hours.
Flask signs these cookies; it does not encrypt their contents.

Applied fix: tokens remain in a bounded server-side session store. The cookie
contains only a random session identifier, which logout revokes immediately.
Sessions have an absolute 12-hour lifetime and a 1,000-session capacity limit.
Login rotates and revokes the previous session; expiry, upstream authentication
rejection, and restarts invalidate access. Legacy token-containing cookies are
discarded. Tests confirm replay cannot access protected routes or make mutations.

References:
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://flask.palletsprojects.com/en/stable/quickstart/#sessions

### Resolved locally — no limit on repeated sign-in attempts

Location: `backend/app.py:204`.

The original semaphore limited simultaneous sign-ins to two, but imposed no attempt limit
over time per account or client. A local test forwarded 20 consecutive failed
sign-ins to the mocked authentication function; none received a local `429`.
The shared outbound API pacer limits total WFM request traffic, but is not a
brute-force defense. Anonymous callers can also consume shared upstream capacity.
Warframe Market may have additional defenses; those were not tested.

Applied fix: five attempts per account and twenty per client address within
fifteen minutes, with `429` and `Retry-After` responses. Counters are bounded,
expire, and reject new keys at capacity rather than reset existing counters.
Local traffic ignores forwarded IP headers. Render traffic is parsed from the
trusted side of its internal/Cloudflare proxy chain; spoofed left-hand entries
cannot change the client's bucket. Tests cover concurrent attempts, rotating
addresses/accounts, cooldowns, memory limits, and spoofed headers.

Reference:
https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

### Resolved locally — missing browser hardening headers

The live login response has no Content-Security-Policy or
Strict-Transport-Security header. HTTP redirects to HTTPS, and the existing
frame, MIME-sniffing, referrer, and cache protections are present.

Applied fix: a CSP permits the React assets, Google Fonts, WFM images, and local
API requests, and blocks inline scripts and embedding. HTTPS responses include
HSTS. A headless Chrome check passed sign-in, dashboard loading, batch polling,
mod image rendering, logout, HTTP-only cookies, and inline-script blocking with
mocked accounts. The live service will receive these headers after deployment.

Reference: https://flask.palletsprojects.com/en/stable/web-security/

### Privacy — personal email remains in published commit metadata

Eight commits expose a personal email in author/committer metadata. No actual
email address is reproduced here. The local repository now uses the GitHub
private email for future commits. Existing published history was preserved,
as requested. Removing historical metadata would require a separately authorized
history rewrite; it cannot reliably erase copies already retained elsewhere.

### Resolved locally — outdated pip

The local virtual environment's pip was upgraded from 23.2.1 to 26.2.1. The
follow-up OSV scan found no advisory matches across all 18 installed packages.
The Render build script upgrades pip before installing application dependencies.
The currently deployed service's pip version was not inspected.

## Checks that passed

- Pattern-based scans of all nine commits found no credential/token/private-key
  matches in repository files. This is a targeted scan, not a guarantee against
  every possible secret format.
- `npm audit` reported zero known dependency vulnerabilities, including development dependencies.
- The follow-up OSV scan reported no matches for all 18 installed Python packages.
- All 33 application/security tests passed; dependency consistency checks passed.
- Frontend lint, production build, and the headless Chrome smoke check passed.
- Unauthenticated creation and deletion requests returned `401` locally.
- Cross-origin sign-in returned `403`; malformed JSON returned `400`;
  non-JSON sign-in returned `415`; oversized input returned `413`.
- Account isolation and order ownership checks passed with mocked accounts.
- The hosted login page returned `200`, and unauthenticated `/status` returned `401`.
- Hosted `.env`, Git configuration, backend source, deployment-helper source,
  and the checked JavaScript source-map path returned `404`.
- The active React code uses escaped rendering rather than raw HTML injection.
  Older HTML templates containing `innerHTML` are not served by the active Flask routes.
- Passwords are forwarded for authentication; application code does not persist
  or deliberately log them.

## Limits

No real account passwords or orders were used in this audit. Authentication
replay and attempt-limit checks ran locally against mocked sign-in responses.
Production cookies were not captured, and no live authentication attack was run.
Accepted background batches may finish after logout; revocation blocks new
session requests. Sessions and attempt counters reset after a process restart,
which is a limitation of the single-worker, in-memory deployment. Cloudflare
proxy ranges must be kept current. Multiple workers require shared storage.
Render account permissions, billing configuration, runtime environment secrets,
and the validity or revocation status of the previously shared API key were not
inspected. Dependency results describe known advisories at audit time and the
tested local environment; they do not establish that every deployed transitive
package has exactly the same version.
