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
   reconstruction (§C)** vs **an undocumented, session-authenticated, HTML-scraping
   client (§B)**. Recommendation in §E: do the former in oktalib, keep the latter out.

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
label, and a **per-app error count**. In the captured org: 10 app instances accounting for
45 errors (largest single app: 15).

Two structural facts matter more than the field list:

- `<ul …-userrows-{appInstanceId}>` is **empty** — the individual user rows are lazy-loaded
  by a further request when the row is expanded. That request was not in the capture, so
  the endpoint that yields *which user* needs action is still unknown.
- `<span class="deprovision-firstresult">0</span>` is a **pagination offset**, so the
  per-app user lists are paged. The `deprovision-` class prefix on the *errors* page
  suggests all categories share one template — i.e. sibling endpoints
  (`/admin/tasks/deprovisioning`, `/admin/tasks/profiles`, …) very likely exist with the
  same shape, but that is inference, not observed.

### B3. Auth and transport

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

## D. Open verification items

**D1 — the deprovisioning question.** On an app configured for manual deprovisioning:
unassign a user in Okta, then check whether the app user *stays* in
`GET /api/v1/apps/{appId}/users` with `status` `UNASSIGNED`/`DEPROVISIONED`/`REVOKED`, or
disappears. Stays → the biggest category (1958 items in the captured org) is reachable
publicly, at the cost of scanning every app's user list. Disappears → it genuinely isn't,
and the README should say so rather than ship an approximation. The presence of
`UNASSIGNED`/`REVOKED` in the enum makes "stays" plausible; it is not proof.

**D2 — is `task.lifecycle.*` the Tasks page?** Trigger a task, then
`GET /api/v1/logs?filter=eventType eq "task.lifecycle.create"&since=…` and inspect
`target[]` — do the targets identify app + user, and is the category distinguishable?

**D3 — do the reconstructions match the console?** Now cheap, because §B1 gives exact
expected numbers. Compare API-derived counts against `numGroupPushErrorsTasks` (84),
`numErrorsTasks` (45), `numProfilesTasks` (155), `numExpiredAppInstancesTasks` (1). Any
mismatch tells us a "medium confidence" row above is wrong. This is the single
highest-value check in this document and needs no further captures.

**D4 — the user-row endpoint** (only if §B is pursued). Expand one app row on the Tasks
page with DevTools open and capture the lazy-load request; that is the one that names the
affected user, and it wasn't in the capture.

## E. Recommendation

**Do not put the internal endpoints in oktalib.** Not on principle — on cost. It would mean
a second auth mechanism (interactive OIDC login + cookie jar + scraped XSRF token) grafted
onto a library whose entire design is a single SSWS-token `requests.Session`, plus an HTML
parser whose contract is a console template that can change in any Okta release, plus an
unknown number of additional requests per app for the user rows. A library that silently
breaks on a Thursday release is worse than one that doesn't have the feature. If this is
needed operationally, it belongs in a script whose owner accepts that maintenance.

**Do ship the primitives.** Each is independently useful, matches existing repo patterns,
and none depends on anything unverified:

| | Change | Where | Size |
| --- | --- | --- | --- |
| E1 | `UserAssignment.status` / `.sync_state` / `.scope` / `.last_sync` | `entities/users.py` (entity exists) | trivial |
| E2 | `GroupPushMapping` entity + `Application.group_push_mappings(status=None)` | new entity + `entities/apps.py` | small |
| E3 | `Application.signing_keys`, `.expiring_signing_keys(days=30)` | `entities/apps.py` | small |
| E4 | `Okta.search_users_by_status(status)` (covers `LOCKED_OUT`) | `oktalib.py` | trivial |
| E5 | `AgentPool` / `Agent` entities + `Okta.agent_pools` | new entity + `oktalib.py` | small |

E1 alone unblocks callers who want to write the deprovisioning scan themselves.

Suggested order: **D3 first** (it validates or kills E1/E2 before any code), then D1, then
E1 → E2/E4 → E3/E5.

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

The HAR used for §B carried a live admin session (`sid`, `JSESSIONID`, `xids`, `DT`,
`proximity_*`) and an XSRF token. None of it is recorded here or anywhere in the repo, and
no user-identifying data from the org's task rows is reproduced — only element/field
structure. Any future capture should stay outside the repo for the same reason.

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
- HAR capture of `/admin/tasks` on a live org, 2026-07-29 — §B
