# Research: implementing Okta "Tasks" in oktalib

Scope: the outstanding items on the Okta Admin Console **Dashboard > Tasks** page —
deprovisioning, provisioning errors, group push errors and friends. Question: what would
it take for oktalib to expose them?

Date: 2026-07-29. Two independent lines of research: the **public Management API** (spec
5.1.0, as vendored in `okta-sdk-python@master`) and the **admin console's own internal
endpoints** (observed from a HAR capture of `/admin/tasks` on a live org).

## Bottom line

1. **There is no public Okta API for Tasks.** Verified against Management API spec 5.1.0:
   117 API modules, 1000 models, **zero** named `*task*`. Okta's own support answer on the
   subject points at *List Users Assigned to Application* as something that "might be of
   help" — an admitted workaround.
2. **The console uses internal endpoints under `/admin/tasks/*`**, and they are good: the
   summary one returns clean JSON that maps 1:1 to the task categories. But they
   authenticate with an **admin session cookie + XSRF token**, not the SSWS token oktalib
   is built on, and the per-category detail endpoints return **HTML fragments**, not JSON.
3. So the choice is not "possible vs impossible" — it's **a documented but partial
   reconstruction (§C)** vs **an undocumented, session-authenticated client (§B)**. The
   internal summary endpoint is better than expected: JSON, and it accepts a
   `selectedUserId` to answer "what's outstanding for this user?" in one request, which
   the public API cannot do at all. The blocker is its **auth model**, not its format.
   Recommendation in §E: build the documented primitives in oktalib, keep the
   session-authenticated route in a separate tool that owns that problem honestly.

## A. What "Tasks" contains

Exact names, from [Monitor your tasks](https://help.okta.com/oie/en-us/content/topics/dashboard/monitor-your-tasks.htm),
grouped as Okta groups them:

**Errors** — Agent down · Application assignments encountered errors · Group push mapping
encountered errors · Profile push updates encountered errors · Renew your expired SAML app
certificates

**To-do** — All imports paused pending threshold review · Application accounts need
deprovisioning · Application accounts need password syncing · Application assignments need
additional information · Application requests waiting · Locked out users · Renew your SAML
app certificates before they expire

**Info** — Applications can be updated to use provisioning · Applications can be updated to
use SAML

## B. The internal endpoints (observed)

`/admin/tasks` itself is the HTML shell — fetched without a session it returns
**302 → `/admin/sso/oidc-entry?fromURI=%2Fadmin%2Ftasks`** and clears `sid`/`xids`. The
data arrives via XHR after load.

### B1. Summary: `GET /admin/tasks/main?taskDate=ALL`

`Content-Type: application/json`. Response (values from one real org):

```json
{
  "numDeprovisioningTasks": 1958,
  "numSyncPasswordTasks": 0,
  "numProvisioningTasks": 0,
  "numErrorsTasks": 45,
  "numProfilesTasks": 155,
  "numInformationTasks": 5,
  "numGroupPushErrorsTasks": 84,
  "numExpiringAppInstancesTasks": 0,
  "numExpiredAppInstancesTasks": 1,
  "numTotalTasks": 2248,
  "pendo": { "isPendoEnabled": false },
  "timeLimitedOrg": { "isTimeLimitedOrg": false, "...": "..." }
}
```

The nine `num*Tasks` fields **sum exactly to `numTotalTasks`** (2248), so this is the
complete and additive task model rather than a partial view. Mapping to §A names:

| JSON field | Task |
| --- | --- |
| `numDeprovisioningTasks` | Application accounts need deprovisioning |
| `numSyncPasswordTasks` | Application accounts need password syncing |
| `numProvisioningTasks` | manual provisioning / assignments need additional information |
| `numErrorsTasks` | Application assignments encountered errors |
| `numProfilesTasks` | Profile push updates encountered errors |
| `numGroupPushErrorsTasks` | Group push mapping encountered errors |
| `numExpiringAppInstancesTasks` | Renew SAML app certificates before they expire |
| `numExpiredAppInstancesTasks` | Renew your expired SAML app certificates |
| `numInformationTasks` | Info tasks (provisioning-capable / SAML-capable apps) |

The `numProvisioningTasks` mapping is the one inference here; the other eight are
unambiguous from the names. Note `pendo` and `timeLimitedOrg` are console UI concerns
leaking into the payload — a sign this is a view-model endpoint, not an API contract.

**The counts move, and unevenly.** Two captures nine days apart:

| Counter | 2026-07-29 | 2026-08-07 | |
| --- | ---: | ---: | ---: |
| `numDeprovisioningTasks` | 1958 | 2157 | +199 |
| `numErrorsTasks` | 45 | 49 | +4 |
| `numGroupPushErrorsTasks` | 84 | 85 | +1 |
| `numProfilesTasks` | 155 | 155 | **0** |
| `numExpiredAppInstancesTasks` | 1 | 1 | 0 |
| `numTotalTasks` | 2248 | 2452 | +204 |

Two consequences. Any reconciliation against the console (D3) has to be **same-moment** —
comparing an API scan to yesterday's console number proves nothing. And `numProfilesTasks`
holding at exactly 155 while everything else grows suggests those items are **stuck rather
than accruing**, which is worth knowing before investing in that category.

**It takes a `selectedUserId`.** `GET /admin/tasks/main?selectedUserId={userId}&taskDate=ALL`
returns the identical nine-field shape scoped to a single user — observed:
`numDeprovisioningTasks: 2`, `numProfilesTasks: 8`, `numTotalTasks: 10`. That is
significant: it answers "what is outstanding for *this* user?" in **one request**, which is
exactly the query the public API cannot express (§C row 7) and which the
scan-every-app workaround would need O(apps) requests to approximate. `taskDate=ALL`
implies other values exist (a date window); none were observed.

### B2. Detail: `GET /admin/tasks/errors?taskDate=ALL`

`Content-Type: text/html; charset=utf-8` — **an HTML fragment, not JSON.** A list of `<li>`
rows, one per app instance:

```html
<li id="errors-instance-row-{appInstanceId}" class="errors-instance-row tasks-instance-row clearfix">
  <div class="task-instance-info clearfix">
    <div class="check-col"><input id="errors-instance-row-checkbox-{appInstanceId}" type="checkbox"/></div>
    <div class="app-icon-mini logo-frame rounded-4"><img src="https://…oktacdn.com/fs/bcg/4/{logoId}"/></div>
    <div class="task-instance-name">
      <h3>{appName}</h3>          <!-- e.g. the OIN app name -->
      <p> {appInstanceLabel}</p>  <!-- e.g. the org's label for that instance -->
    </div>
    <div id="errors-instance-row-count-{appInstanceId}" class="task-instance-count rounded-4">{count}</div>
    <a id="errors-instance-row-showlink-{appInstanceId}" class="…instance-toggle" href="#">…</a>
    <a id="errors-instance-row-hidelink-{appInstanceId}" class="…instance-toggle" href="#">…</a>
  </div>
  <ul id="errors-instance-row-userrows-{appInstanceId}"></ul>
  <span id="errors-firstresult-{appInstanceId}" class="deprovision-firstresult">0</span>
</li>
```

Extractable per row: **app instance id** (`0oa…`, from the element id), app name, instance
label, and a **per-app count**. The element id prefix and `data-task-type` track the
category, so the *profiles* variant emits `profiles-instance-row-{appInstanceId}` and so on.

`<ul …-userrows-{appInstanceId}>` arrives **empty** — user rows are lazy-loaded per app
(§B3). `<span class="deprovision-firstresult">0</span>` is the pagination offset for that
lazy load; note the `deprovision-` class prefix appears on *every* category, confirming one
shared template.

**Both fragments reconcile exactly against §B1**, which is the strongest evidence that these
are the authoritative task lists rather than a filtered view:

| Fragment | App instances | Rows sum to | Matching counter |
| --- | --- | --- | --- |
| `/admin/tasks/errors` | 10 | **45** | `numErrorsTasks` 45 |
| `/admin/tasks/profiles` | 28 | **155** | `numProfilesTasks` 155 |

#### Which detail routes exist

Okta's admin router returns **404 for unknown paths before the auth redirect**, and **302 to
`/admin/sso/oidc-entry` for paths that exist**. That difference is an unauthenticated
route-existence oracle — no credentials needed. Probing it:

| Route | |
| --- | --- |
| `/admin/tasks`, `/admin/tasks/main`, `/admin/tasks/errors` | exist (also observed in captures) |
| `/admin/tasks/profiles`, `/admin/tasks/deprovisioning`, `/admin/tasks/information` | **exist** |
| grouppush / syncpassword / provisioning / expiring / expired, ~13 name variants | **no route** |

So four detail routes serve nine counters. Since `numGroupPushErrorsTasks` (85) and
`numExpiredAppInstancesTasks` (1) are non-zero and must render somewhere, those categories
are presumably parameters on the existing routes rather than routes of their own.

Caveat on the oracle: it discriminates on **path only**. Query strings are not routed, so
`/admin/tasks?type=profiles` and `/admin/tasks?type=utter-nonsense` both return 302 — a
`type=` parameter can be neither confirmed nor refuted this way.

### B3. Per-user rows: `GET /admin/tasks/{type}/instance`

Expanding an app row fires:

```
GET /admin/tasks/errors/instance?taskDate=ALL&instanceId={appInstanceId}&firstResult=0
```

`text/html`, one `<li>` per affected user. **This is the only place the error reason
exists** — nothing in the public API carries it (§C).

| Field | Location in the markup |
| --- | --- |
| task id | `<li id="errors-user-row-{taskId}">` — `aat…` |
| app user id | `<span class="hidden-appuser-id">` — `0ua…` |
| Okta user id | `data-user-id` on the Edit Assignment input — `00u…` |
| app instance id | `data-instance-id` |
| category | `data-task-type` (`errors`, presumably `profiles` etc.) |
| user display name | `<h4>` inside `.user-info` |
| user email | `<p class="text-light">` inside `.user-info` |
| **error headline** | `<div class="infobox infobox-error"><h3>` |
| **error detail** | the `<p>` following that `<h3>` |
| created timestamp | inline JS: `new Date('2026-07-10 07:37:22.0')` |

Observed error details, showing the granularity available:

```
Automatic provisioning of user … to app Okta Org2Org failed:
    Error while creating user …: HTTP 404 Not Found
    Error while creating user …: Expectation Failed. Errors reported by remote server:
        Not enough licenses available
    Error while creating user …: Api validation failed: password (password: Password
        requirements were not met. …)
```

**Row counts reconcile with the parent fragment**: Jumbo Org2Org listed 5 → 5 rows returned;
two single-item apps listed 1 → 1 row each.

There is also a **remediation** path, not just read access. The Edit Assignment form posts to:

```
POST /app/{appName}/admin/profile/retry/{appUserId}/{taskId}
     _xsrfToken=…&userName=…&extensibleProfile[…]=…
```

so retrying a failed assignment is reachable the same way. `{appName}` is the app *type*
slug (`okta_org2org`, or `{org}_{oinappname}_{n}` for a custom integration), not the
instance id.

#### The category question this answers

Every row here carries `data-task-type="errors"` with the headline *"An error occurred while
assigning this app"*. So **`errors` = assignment failures**, definitively. By symmetry the
profiles category should be `/admin/tasks/profiles/instance?…` with `data-task-type="profiles"`
and its own headline — unconfirmed, and the single remaining unknown for implementing
profile-push errors by this route. One expand-a-row capture under *Profile push updates
encountered errors* settles both the endpoint and whether its rows carry a distinct reason.

### B4. The console also calls the *public* API

Not everything the Tasks page does is internal. The user-picker on that page issues:

```
GET https://{org}-admin.okta-emea.com/api/v1/users
    ?q=&limit=10&sortBy=profile.lastName&timestamp={epoch_ms}
    &search=(status eq "ACTIVE" or status eq "STAGED" or status eq "PROVISIONED"
             or status eq "RECOVERY" or status eq "PASSWORD_EXPIRED"
             or status eq "LOCKED_OUT" or status eq "SUSPENDED"
             or status eq "DEPROVISIONED")
        and (profile.firstName sw "{term}" or profile.lastName sw "{term}"
             or profile.login sw "{term}" or profile.email sw "{term}")
```

Three things worth noting:

- This is the **documented** `/api/v1/users` endpoint, and its `Link: rel="self"` response
  header points back at the **org** host (`https://{org}.okta-emea.com/api/v1/users?…`) —
  the admin host just fronts the same API. So it is reachable with an SSWS token from
  oktalib as-is.
- `x-rate-limit-limit: 600` here versus **250** on `/admin/tasks/*` — confirming the
  internal console endpoints sit in a separate, tighter bucket.
- The `search=` expression syntax is directly reusable: `status eq "…"` combined with
  `sw` (starts-with) over `profile.*`, plus `sortBy`. oktalib's `search_users` /
  `search_users_by_email` currently use only `?q=` and `?filter=`, which can't express
  this. See E6.

### B5. Auth and transport

- **Cookies**: `sid`, `JSESSIONID`, `xids`, `DT`, `proximity_*`. Session-scoped;
  `srefresh` is re-issued per response with `Max-Age=1800`, and `smax` caps the session.
- **Headers**: `X-Okta-XsrfToken: <token>` and `X-Requested-With: XMLHttpRequest`. The XSRF
  token is minted into the console HTML, so a client would have to scrape it from
  `/admin/tasks` first.
- **Host**: the separate `*-admin.okta-emea.com` host, not the org host oktalib targets.
- **Rate limit**: `x-rate-limit-limit: 250` (separate bucket from the public API).
- SSWS tokens are **not** accepted on `/admin/*`.

So a client here needs: an interactive admin login (OIDC, likely MFA) → session cookies →
scrape the XSRF token → JSON for counts, HTML parsing for detail, plus a second unknown
request per app for user rows. None of it is version-guaranteed.

## C. The documented-API reconstruction

What the public API *can* do, per category. Confidence is about whether the endpoint
reproduces the console's list, not whether it exists.

| Task | Documented endpoint | Server-side filter | Confidence |
| --- | --- | --- | --- |
| Group push mapping errors | `GET /api/v1/apps/{appId}/group-push/mappings` | **yes** — `status`, `sourceGroupId` | **high** |
| Agent down | `GET /api/v1/agentPools` | no (`after`, `limit`) | **high** |
| Renew SAML certs (expired + expiring) | `GET /api/v1/apps/{appId}/credentials/keys` → `expiresAt` | no | **high** |
| Locked out users | `GET /api/v1/users?filter=status eq "LOCKED_OUT"` | **yes** | **high** |
| Assignment errors | `GET /api/v1/apps/{appId}/users` → `syncState == ERROR` | no | medium (inferred) |
| Profile push errors | same, `syncState in (ERROR, OUT_OF_SYNC)` | no | low — likely not separable from the above |
| **Accounts need deprovisioning** | none; candidate is `/api/v1/apps/{appId}/users` → `status in (UNASSIGNED, DEPROVISIONED, REVOKED)` | no | **unverified** — see §D1 |
| Accounts need password syncing | none; candidate is app-user `credentials` / `passwordChanged` | no | low |
| Assignments need additional information | none; candidate is app user missing required profile attrs | no | low |
| Application requests waiting | Okta Identity Governance *Access Requests* API — separate product and base path | n/a | out of scope |
| Imports paused pending threshold review | none found (Reports > Import Monitoring is UI-only) | n/a | **not possible** |
| Apps can be updated to use provisioning / SAML | none found (Reports pages) | n/a | **not possible** |

### Object shapes (from spec 5.1.0)

`AppUser` — items of `/api/v1/apps/{appId}/users`. Already modelled in oktalib as
`UserAssignment` (`src/oktalib/entities/users.py:685`), which exposes only `email` and
`user`/`group`. The fields that matter here are all unexposed:

- `status`: `ACTIVE APPROVED DEPROVISIONED IMPLICIT IMPORTED INACTIVE MATCHED PENDING PROVISIONED REVOKED STAGED SUSPENDED UNASSIGNED`
- `syncState`: `DISABLED ERROR OUT_OF_SYNC SYNCHRONIZED SYNCING`
- `scope` (`USER` vs `GROUP` — the individual-vs-group-assignment distinction the Tasks
  page surfaces), `lastSync`, `statusChanged`, `passwordChanged`, `externalId`

`GroupPushMapping` — `/api/v1/apps/{appId}/group-push/mappings`, not modelled: `id`,
`status` (`ACTIVE ERROR INACTIVE`), `errorSummary`, `sourceGroupId`, `targetGroupId`,
`lastPush`, `created`, `lastUpdated`. List params: `after`, `limit`, `sourceGroupId`,
`status`.

`AgentPool` — `/api/v1/agentPools`, not modelled: `operationalStatus`
(`OPERATIONAL DEGRADED DISRUPTED INACTIVE`), `disruptedAgents`, `inactiveAgents`, plus
embedded `agents[]` each with `operationalStatus`, `lastConnection`, `version`,
`updateStatus`, `updateMessage`.

`JsonWebKey` — `/api/v1/apps/{appId}/credentials/keys`, not modelled: `kid`, `created`,
`expiresAt`, `lastUpdated`, `use`, `kty`. Expiry is client-side arithmetic on `expiresAt`;
the app list must be narrowed to SAML apps first.

### System Log

Okta's official event catalogue (`developer.okta.com/docs/okta-event-types.csv`, 1146
events) has a `task`-tagged family, present since release 2018.15:

```
task.lifecycle.create      "Created system task."
task.lifecycle.update      "Updated system task."
task.lifecycle.activate    "Activated system task."
task.lifecycle.deactivate  "Deactivated system task."
task.lifecycle.delete      "Deleted system task."
system.org.task.remove     "Tasks removed."     (tag: system)
```

Task creation/removal is therefore auditable via `GET /api/v1/logs` even though the queue
isn't readable. That yields an event feed, not current state — you'd fold create/delete
events yourself, with the usual retention-window and missed-event correctness problems.
Unverified that `task.lifecycle.*` means Tasks-page items rather than some other internal
notion of "system task" (§D2). oktalib doesn't wrap `/api/v1/logs` at all today.

## C-bis. Request cost, and the per-user shortcut

An earlier draft of this document claimed items over app users and certificates were both
`O(apps × users)`. That was wrong, and the correction matters for prioritisation:

| Query | Requests |
| --- | --- |
| Tasks for one **user** | **1 paginated call** — see below |
| Tasks for one **app** | O(app's users ÷ 200) — no server-side predicate exists |
| Certificates expiring org-wide | O(signing apps) — one per app, *not* per user |
| Group push errors org-wide | O(apps), with server-side `status=ERROR` |
| Org-wide app-user rollup | expensive, and inherently so |

Certificates are one request per app because keys are only reachable per app; there is no
org-wide key listing. Narrowing to apps that actually sign assertions is free, because
`signOnMode` is already in the `/api/v1/apps` listing.

The per-user case needs no scanning at all. Per the spec, `/api/v1/apps` supports:

> `expand` — "Only supports `expand=user/{userId}` and must be used with the
> `user.id eq "{userId}"` filter query for the same user. Returns the assigned application
> user in the `_embedded` property."

```
GET /api/v1/apps?filter=user.id eq "{userId}"&expand=user/{userId}
```

That returns every app assigned to the user with the app-user object (`status`, `syncState`,
`scope`) embedded — the documented public equivalent of the console's `selectedUserId`
(§B1). Caveat to verify: the `filter` parameter's own documentation lists supported
properties as `id`, `status`, `credentials.signing.kid`, `settings.slo.enabled`, `name` and
omits `user.id`, even though the `expand` documentation mandates pairing with `user.id eq`.
The docs contradict each other; one curl against a real org settles it.

## D. Open verification items

**D1 — the deprovisioning question.** *Deprioritised — "Application accounts need
deprovisioning" is not a priority for this org, despite being 1958 of 2248 tasks.* Kept for
the record: on an app configured for manual deprovisioning, unassign a user in Okta, then
check whether the app user *stays* in `GET /api/v1/apps/{appId}/users` with `status`
`UNASSIGNED`/`DEPROVISIONED`/`REVOKED`, or disappears. Stays → reachable publicly at the
cost of the org-wide scan above. Disappears → not implementable, and the README should say
so rather than ship an approximation. The presence of `UNASSIGNED`/`REVOKED` in the enum
makes "stays" plausible; it is not proof.

**D2 — is `task.lifecycle.*` the Tasks page?** Trigger a task, then
`GET /api/v1/logs?filter=eventType eq "task.lifecycle.create"&since=…` and inspect
`target[]` — do the targets identify app + user, and is the category distinguishable?

**D3 — do the reconstructions match the console?** Now cheap, because §B1 gives exact
expected numbers. Compare API-derived counts against `numGroupPushErrorsTasks` (84),
`numErrorsTasks` (45), `numProfilesTasks` (155), `numExpiredAppInstancesTasks` (1). Any
mismatch tells us a "medium confidence" row above is wrong. This is the single
highest-value check in this document and needs no further captures.

**D4 — the user-row endpoint.** *Closed* — it is
`GET /admin/tasks/{type}/instance?taskDate=ALL&instanceId={appId}&firstResult={offset}`,
documented in §B3. It names the user *and* carries the error reason, and a retry POST exists
alongside it.

**D5 — the profiles user-row variant.** The one thing still open. Expand an app row under
*Profile push updates encountered errors* with DevTools on XHR. It confirms
`/admin/tasks/profiles/instance`, its `data-task-type`, and — the part that matters —
whether profile-push rows carry a reason distinct from the assignment errors in §B3. If they
do, the scrape fully subsumes the System Log route for this category; if they don't, the log
is the only way to tell the two apart.

## E. Recommendation

**Do not put the internal endpoints in oktalib** — but the reason is narrower than it first
appears, so it's worth stating precisely.

The HTML-scraping objection only applies to the **detail** endpoints (§B2, §B3). The
**summary** endpoint (§B1) is clean JSON, and with `selectedUserId` it answers the per-user
question in one request — something the public API genuinely cannot do. If the requirement is
"how many tasks are outstanding, org-wide or for user X", the internal route is *one JSON GET*
and the documented route is O(apps × users) requests that may not even be able to answer it
(§D1).

The gap is wider than counts, and §B3 is what settles it. Three things exist only internally:

1. **The error reason.** `AppUser.syncState` is an enum with five values and no reason field;
   the console shows *"Not enough licenses available"*, *"HTTP 404 Not Found"*,
   *"Password requirements were not met"*. No public endpoint carries that string.
2. **Category separation.** `data-task-type` distinguishes assignment failures from profile
   pushes; `syncState` cannot (§C rows 5–6).
3. **Remediation.** The retry POST re-drives a failed assignment. The public API has no
   equivalent "retry this task" call.

So on capability the internal route wins outright, and it is not close. That is worth stating
plainly rather than burying, because it means the recommendation below is a trade — not a
case of the documented API being just as good.

What still rules it out for this library is **auth**, not parsing: it needs an interactive
admin OIDC login (likely MFA), a cookie jar with a 30-minute sliding session, and an XSRF
token scraped out of the console HTML — grafted onto a library whose entire design is one
SSWS-token `requests.Session`. Add a 250/min shared bucket and a payload that carries
`pendo` UI flags, and it is a console view-model that can change in any release, not an
interface. A library that silently breaks on a Thursday release is worse than one that
doesn't have the feature.

If someone needs those numbers operationally, the honest shape is a **separate script or
tool** that owns the browser-session problem explicitly — not an oktalib method that
pretends the auth model is the same. Worth revisiting only if Okta ever exposes
`/admin/tasks/main`'s data under `/api/v1` with token auth.

**Do ship the primitives.** Each is independently useful, matches existing repo patterns,
and none depends on anything unverified:

| | Change | Where | Size | Status |
| --- | --- | --- | --- | --- |
| E3 | `AppKey` / `AppSigningCertificate` entities, `Application.signing_certificates`, `.expiring_signing_certificates(days)`, `Okta.get_expiring_app_certificates(days)` / `.get_expired_app_certificates()` | `entities/apps.py`, `oktalib.py` | small | **done** |
| E2 | `GroupPushMapping` entity + `Application.group_push_mappings(status=None)` | new entity + `entities/apps.py` | small | todo |
| E6 | `search=` support (`status eq`, `profile.* sw`, `sortBy`) — syntax proven in §B4; subsumes a status-only helper | `oktalib.py` | small | todo |
| E5 | `AgentPool` / `Agent` entities + `Okta.agent_pools` | new entity + `oktalib.py` | small | todo |
| E1 | `UserAssignment.status` / `.sync_state` / `.scope` / `.last_sync` | `entities/users.py` (entity exists) | trivial | todo |
| E7 | `User.app_assignments()` via the filter+expand shortcut in §C-bis | `entities/users.py` | small | blocked on the `user.id` filter check |

E6 is the most broadly useful of the remainder: `search=` is strictly more capable than the
`?q=` the library uses today. E1 is trivial and unblocks callers writing their own scans.

### Two design decisions worth recording (E3)

**The key entity must override `id`.** Okta identifies application keys by `kid`, not `id`.
`Entity.id` reads `_data['id']` and both `__hash__` and `__eq__` are built on it, so
inheriting unchanged makes *every* key hash to `hash('')` and compare equal to every other
key — two certificates collapse to one in a `set()`. Overriding `id` to return `kid` fixes
identity and keeps the inherited `created_at`/`last_updated_at`, which work because the
payload does use `created` and `lastUpdated`. The key payload carries no app id either, so
the entity takes its parent app's data to build `url`, matching `ClientSecret`.

**The class split is expiry, not SAML.** `/api/v1/apps/{appId}/credentials/keys` is not
SAML-scoped — it is the app signing key store, and WS-Fed apps have signing certificates
too, which is why `Okta.get_expiring_app_certificates` narrows on
`SIGNING_SIGN_ON_MODES = (SAML_2_0, WS_FEDERATION)` rather than SAML alone. The real
distinction is that x509 signing certificates expire while the JSON Web Keys used for
`private_key_jwt` client authentication (which this library already *creates* via
`create_api_services_app_with_jwks`) do not. So `AppKey` holds the shared JWK fields and
`AppSigningCertificate` adds `expires_at` / `is_expired` / `expires_within` / `x509_chain` /
`thumbprint`. A future `AppJsonWebKey` slots in beside it.

Suggested order for the rest: **D3 first** (it validates or kills E2 before any code), then
E6 → E2 → E5 → E1, with E7 after the `user.id` filter check.

An aggregating `Okta.tasks` façade over E1–E5 is tempting but will never match the console
(§C rows 7–12 are partly or wholly unavailable), so it invites trust in a quietly
incomplete number. If it is ever built, name the pieces for what they are —
`pending_deprovisions()`, `failed_group_pushes()` — not `tasks()`.

## F. Open questions for the reviewer

1. Is *Application accounts need deprovisioning* the actual driver? At 1958 of 2248 tasks
   in the captured org it dominates, and it is the one category with no documented
   endpoint. If yes, D1 is the whole decision.
2. Is Okta Identity Governance licensed in the target orgs? That decides whether
   *Application requests waiting* is reachable at all, and whether an IGA base-path client
   belongs in oktalib.
3. Is a scan-every-app implementation acceptable? E1/E2/E3 all iterate apps and then their
   users — O(apps × users) requests against a rate-limited API.

## Note on the capture

Four HARs informed §B, each carrying a live admin session (`sid`, `JSESSIONID`, `xids`, `DT`,
`proximity_*`) and an XSRF token. Beyond the session material they contained real personal
data: the §B4 user search returned a full profile — including a `tacacsHash` (a `$6$`
SHA-512 crypt hash), phone numbers, employee number and home-adjacent address — and the §B3
user rows named affected employees with their email addresses, job titles, managers and
employee numbers.

None of that is recorded here or anywhere in the repo. This document reproduces only endpoint
paths, parameter names, field names and element structure. No cookie, token, user id, app
instance id, email, personal name or profile value appears; the error strings are quoted with
identifying parts elided. The verified counts (45, 155, 2248, 2452 …) are aggregates.

Three follow-ups for whoever owns the org, independent of this research:

- Rotate whatever credential `profile.tacacsHash` derives from, and review whether a password
  hash belongs in an Okta profile attribute that any admin-console user search returns in
  cleartext JSON.
- Note that one observed error string echoes the org's **full password policy** back into the
  task list, where it is readable by anyone with admin console access.
- Future captures should stay outside the repo, and be scrubbed before pasting anywhere.

## Sources

- [Monitor your tasks (Identity Engine)](https://help.okta.com/oie/en-us/content/topics/dashboard/monitor-your-tasks.htm)
- [Monitor your tasks (Classic)](https://help.okta.com/en-us/content/topics/dashboard/monitor-your-tasks.htm)
- [Managing manual provisioning and deprovisioning tasks](https://support.okta.com/help/s/article/managing-manual-provisioning-and-deprovisioning-tasks?language=en_US)
- [How do I complete manual provisioning and deprovisioning tasks?](https://support.okta.com/help/s/article/How-do-I-complete-manual-provisioning-and-deprovisioning-tasks?language=en_US)
- [API to retrieve app accounts need deprovisioning (support forum)](https://support.okta.com/help/s/question/0D54z00009GWeqiCAD/api-to-retrieve-app-accounts-need-deprovisioning-okta-dashboard-tasks?language=en_US)
- [Okta event types catalogue (CSV)](https://developer.okta.com/docs/okta-event-types.csv)
- [Event Types reference](https://developer.okta.com/docs/reference/api/event-types/)
- [System Log query reference](https://developer.okta.com/docs/reference/system-log-query/)
- [Core Okta API](https://developer.okta.com/docs/reference/core-okta-api/)
- Okta Management API OpenAPI spec 5.1.0, as vendored in [okta-sdk-python](https://github.com/okta/okta-sdk-python)
  (`okta/api/*.py`, `okta/models/*.py`) — endpoint paths, model fields, enums
- HAR captures of `/admin/tasks` on a live org — §B:
  2026-07-29 (page load: `main` + `errors`), 2026-07-29 (user picker + `selectedUserId`),
  2026-08-07 (`profiles` fragment), 2026-08-07 (`errors/instance` user rows + retry form)
- Unauthenticated route probing of `/admin/tasks/*` on the same org, 2026-08-07 — §B2
