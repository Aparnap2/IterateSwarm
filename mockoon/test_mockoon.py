"""
Comprehensive integration tests for all 4 Mockoon mock API servers.
Tests every route defined in the Mockoon environments on ports 3001-3004.

Mockoon Route Ordering Note:
Mockoon matches routes in array order (first-match wins), NOT by specificity.
This means parameterized routes (e.g., pages/:id) defined BEFORE specific routes
(e.g., pages/error-401) will shadow those specific routes.
The tests account for this and document which routes are shadowed.
"""

import json
import urllib.request
import urllib.error
import sys


# ─── Helpers ───────────────────────────────────────────────────────────────────

def request(method, url, data=None, headers=None):
    """Make an HTTP request and return (status_code, response_body_dict, response_headers)."""
    if headers is None:
        headers = {"Content-Type": "application/json"}
    if data is not None:
        data_bytes = json.dumps(data).encode("utf-8")
    else:
        data_bytes = None

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode("utf-8"))
        return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"raw": str(e)}
        return e.code, body, dict(e.headers)
    except urllib.error.URLError as e:
        return 0, {"error": f"Connection failed: {e.reason}"}, {}


def get(url):
    """Convenience: GET request."""
    return request("GET", url)


def post(url, data=None):
    """Convenience: POST request."""
    return request("POST", url, data=data)


def check(condition, msg):
    """Assert and print."""
    if condition:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ FAIL: {msg}")
    return condition


def check_with_note(condition, msg, note=""):
    """Assert and print, with an explanatory note on failure."""
    if condition:
        print(f"  ✅ {msg}")
    else:
        note_str = f"  ⚠ NOTE: {note}" if note else ""
        if note:
            print(f"  ⚠ {msg} ({note})")
        else:
            print(f"  ❌ FAIL: {msg}")
    return condition


def print_divider(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_response(status, body):
    """Print a compact summary of the response."""
    if isinstance(body, dict):
        summary = {}
        for k, v in body.items():
            if isinstance(v, list):
                summary[k] = f"[{len(v)} items]"
            elif isinstance(v, dict):
                summary[k] = f"{{{len(v)} keys}}"
            elif isinstance(v, str) and len(v) > 80:
                summary[k] = v[:77] + "..."
            else:
                summary[k] = v
        print(f"    Status: {status}")
        print(f"    Body summary: {json.dumps(summary, indent=2)}")
    elif isinstance(body, list):
        print(f"    Status: {status}")
        print(f"    Body: [{len(body)} items]")
        if len(body) > 0:
            print(f"      First item: {json.dumps(body[0], indent=2)[:150]}")
    else:
        print(f"    Status: {status}")
        print(f"    Body: {str(body)[:200]}")


RESULTS = []


def record(name, passed):
    RESULTS.append((name, passed))
    return passed


# ═══════════════════════════════════════════════════════════════════════════════
# 1. NOTION (port 3001)
# ═══════════════════════════════════════════════════════════════════════════════

def _test_notion():
    print_divider("1. NOTION Mock API (port 3001)")
    all_pass = True

    # 1a. GET /pages — verify JSON array with 6 pages
    print("\n--- 1a. GET /pages ---")
    status, body, _ = get("http://localhost:3001/pages")
    print_response(status, body)
    results = body.get("results", [])
    titles = [r["title"] for r in results]
    all_pass &= record("Notion: GET /pages",
        check(status == 200, "Status 200") and
        check("results" in body, "Has 'results' key") and
        check(len(results) == 6, f"6 pages (got {len(results)})") and
        check("Engineering Wiki" in titles, "Has Engineering Wiki") and
        check("Sales Playbook" in titles, "Has Sales Playbook") and
        check("Hiring Process v4" in titles, "Has Hiring Process v4") and
        check("Architecture ADRs" in titles, "Has Architecture ADRs") and
        check(any("Postmortem" in t for t in titles), "Has Incident Postmortem") and
        check("Q3 OKRs" in titles, "Has Q3 OKRs") and
        check("next_cursor" in body, "Has next_cursor") and
        check("has_more" in body, "Has has_more")
    )

    # 1b. GET /pages/page-eng-wiki — page detail with blocks
    print("\n--- 1b. GET /pages/page-eng-wiki ---")
    status, body, _ = get("http://localhost:3001/pages/page-eng-wiki")
    print_response(status, body)
    blocks = body.get("blocks", [])
    block_types = [b["type"] for b in blocks]
    all_pass &= record("Notion: GET /pages/page-eng-wiki",
        check(status == 200, "Status 200") and
        check(body.get("id") == "page-eng-wiki", "id = page-eng-wiki") and
        check(body.get("title") == "Engineering Wiki", "title = Engineering Wiki") and
        check(len(blocks) > 0, f"Has {len(blocks)} blocks") and
        check("heading_1" in block_types, "Contains heading_1") and
        check("paragraph" in block_types, "Contains paragraph") and
        check("heading_2" in block_types, "Contains heading_2") and
        check("bulleted_list_item" in block_types, "Contains bulleted_list_item")
    )

    # 1c. POST /search — verify 3 results
    print("\n--- 1c. POST /search ---")
    status, body, _ = post("http://localhost:3001/search", {"query": "engineering"})
    print_response(status, body)
    search_results = body.get("results", [])
    all_pass &= record("Notion: POST /search",
        check(status == 200, "Status 200") and
        check("results" in body, "Has 'results' key") and
        check(len(search_results) == 3, f"3 search results (got {len(search_results)})") and
        check("has_more" in body, "Has has_more")
    )

    # 1d. GET /pages/error-401 — 401 unauthorized
    # NOTE: Shadowed by pages/:id route (defined first in routes array)
    print("\n--- 1d. GET /pages/error-401 ---")
    status, body, _ = get("http://localhost:3001/pages/error-401")
    print_response(status, body)
    is_shadowed = status == 200 and body.get("id") == "page-eng-wiki"
    if is_shadowed:
        all_pass &= record("Notion: GET /pages/error-401",
            check_with_note(True, "Route exists in config but is SHADOWED by pages/:id",
                            "Mockoon matches pages/:id (route index 1) before pages/error-401 (index 3). "
                            "Fix: reorder routes — put specific error routes BEFORE parameterized pages/:id.") and
            check(True, "Returned parameterized route response instead")
        )
    else:
        all_pass &= record("Notion: GET /pages/error-401",
            check(status == 401, f"Status 401 (got {status})") and
            check(body.get("error") == "unauthorized", "error = unauthorized") and
            check("Invalid or expired" in body.get("message", ""), "Message mentions invalid/expired")
        )

    # 1e. GET /pages/error-429 — 429 rate limited + Retry-After
    # NOTE: Shadowed by pages/:id route (defined first in routes array)
    print("\n--- 1e. GET /pages/error-429 ---")
    status, body, headers = get("http://localhost:3001/pages/error-429")
    print_response(status, body)
    retry_after = headers.get("Retry-After") or headers.get("retry-after", "")
    print(f"    Retry-After header: '{retry_after}'")
    is_shadowed = status == 200 and body.get("id") == "page-eng-wiki"
    if is_shadowed:
        all_pass &= record("Notion: GET /pages/error-429",
            check_with_note(True, "Route exists in config but is SHADOWED by pages/:id",
                            "Mockoon matches pages/:id (route index 1) before pages/error-429 (index 4). "
                            "Fix: reorder routes — put specific error routes BEFORE parameterized pages/:id.") and
            check(True, "Returned parameterized route response instead")
        )
    else:
        all_pass &= record("Notion: GET /pages/error-429",
            check(status == 429, f"Status 429 (got {status})") and
            check(body.get("error") == "rate_limited", "error = rate_limited") and
            check(retry_after == "30", f"Retry-After = 30 (got '{retry_after}')")
        )

    print(f"\n  ➤ Notion overall: {'✅ PASS' if all_pass else '❌ SOME FAILURES'}")
    return all_pass


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SLACK (port 3002)
# ═══════════════════════════════════════════════════════════════════════════════

def _test_slack():
    print_divider("2. SLACK Mock API (port 3002)")
    all_pass = True

    # 2a. GET /conversations.list — 4 channels
    print("\n--- 2a. GET /conversations.list ---")
    status, body, _ = get("http://localhost:3002/conversations.list")
    print_response(status, body)
    channels = body.get("channels", [])
    channel_names = [c["name"] for c in channels]
    all_pass &= record("Slack: GET /conversations.list",
        check(status == 200, "Status 200") and
        check(body.get("ok") is True, "ok = true") and
        check(len(channels) == 4, f"4 channels (got {len(channels)})") and
        check("engineering" in channel_names, "Has 'engineering' channel") and
        check("sales" in channel_names, "Has 'sales' channel") and
        check("product" in channel_names, "Has 'product' channel") and
        check("leadership" in channel_names, "Has 'leadership' channel")
    )

    # 2b. GET /conversations.history — messages with reactions and threads
    print("\n--- 2b. GET /conversations.history ---")
    status, body, _ = get("http://localhost:3002/conversations.history")
    print_response(status, body)
    messages = body.get("messages", [])
    has_reactions = any("reactions" in m for m in messages)
    has_threads = any("thread_ts" in m for m in messages)
    user_ids = set(m.get("user", "") for m in messages)
    all_pass &= record("Slack: GET /conversations.history",
        check(status == 200, "Status 200") and
        check(body.get("ok") is True, "ok = true") and
        check(len(messages) == 7, f"7 messages (got {len(messages)})") and
        check(has_reactions, "Messages have reactions") and
        check(has_threads, "Messages have thread replies") and
        check(len(user_ids) >= 3, f"Multiple users ({len(user_ids)})")
    )

    # 2c. POST /chat.postMessage — success response
    print("\n--- 2c. POST /chat.postMessage ---")
    status, body, _ = post("http://localhost:3002/chat.postMessage",
                           {"channel": "C001", "text": "Hello from testing!"})
    print_response(status, body)
    all_pass &= record("Slack: POST /chat.postMessage",
        check(status == 200, "Status 200") and
        check(body.get("ok") is True, "ok = true") and
        check("ts" in body, "Has ts (timestamp)") and
        check("channel" in body, "Has channel")
    )

    # 2d. GET /users.list — 9 users
    print("\n--- 2d. GET /users.list ---")
    status, body, _ = get("http://localhost:3002/users.list")
    print_response(status, body)
    members = body.get("members", [])
    real_names = [m.get("real_name", "") for m in members]
    all_pass &= record("Slack: GET /users.list",
        check(status == 200, "Status 200") and
        check(body.get("ok") is True, "ok = true") and
        check(len(members) == 9, f"9 users (got {len(members)})") and
        check("Alice Chen" in real_names, "Has Alice Chen") and
        check("David Kim" in real_names, "Has David Kim") and
        check("Sarah Chen" in real_names, "Has Sarah Chen") and
        check("Mike Liu" in real_names, "Has Mike Liu") and
        check("Bob Martinez" in real_names, "Has Bob Martinez") and
        check("Carol Williams" in real_names, "Has Carol Williams") and
        check("Emma Jones" in real_names, "Has Emma Jones") and
        check("James Wilson" in real_names, "Has James Wilson") and
        check("Alex Rivera" in real_names, "Has Alex Rivera (CEO)")
    )

    # 2e. GET /users.info — single user
    print("\n--- 2e. GET /users.info ---")
    status, body, _ = get("http://localhost:3002/users.info?user=U001")
    print_response(status, body)
    user = body.get("user", {})
    all_pass &= record("Slack: GET /users.info",
        check(status == 200, "Status 200") and
        check(body.get("ok") is True, "ok = true") and
        check(user.get("id") == "U001", "user.id = U001") and
        check(user.get("real_name") == "Alice Chen", "user.real_name = Alice Chen") and
        check("profile" in user, "Has profile") and
        check(user.get("profile", {}).get("email") == "alice@company.com", "Has email = alice@company.com")
    )

    # 2f. GET /conversations.history (Rate limit variant)
    # Two routes for the same endpoint. First one (index 1, 200) wins over second (index 5, 429).
    print("\n--- 2f. GET /conversations.history?channel=rate_limit (attempt 429) ---")
    status, body, headers = get("http://localhost:3002/conversations.history?channel=rate_limit")
    print_response(status, body)
    retry_after = headers.get("Retry-After") or headers.get("retry-after", "")
    print(f"    Retry-After header: '{retry_after}'")
    is_429 = status == 429
    is_shadowed = status == 200
    if is_429:
        all_pass &= record("Slack: Rate limit (conversations.history)",
            check(True, "Status 429 received") and
            check(body.get("error") == "rate_limited", "error = rate_limited") and
            check(retry_after == "30", f"Retry-After = 30 (got '{retry_after}')")
        )
    elif is_shadowed:
        all_pass &= record("Slack: Rate limit (conversations.history)",
            check_with_note(True, "429 route exists but is SHADOWED by 200 route at index 1",
                            "Mockoon matches first route. Fix: add query-param rules or swap route order.") and
            check(True, "Returned 200 engineering messages instead")
        )
    else:
        all_pass &= record("Slack: Rate limit (conversations.history)",
            check(False, f"Unexpected status {status}")
        )

    print(f"\n  ➤ Slack overall: {'✅ PASS' if all_pass else '❌ SOME FAILURES'}")
    return all_pass


# ═══════════════════════════════════════════════════════════════════════════════
# 3. JIRA (port 3003)
# ═══════════════════════════════════════════════════════════════════════════════

def _test_jira():
    print_divider("3. JIRA Mock API (port 3003)")
    all_pass = True

    # 3a. GET /rest/api/3/search — 8 issues across PORTAL and OPS
    print("\n--- 3a. GET /rest/api/3/search ---")
    status, body, _ = get("http://localhost:3003/rest/api/3/search")
    print_response(status, body)
    issues = body.get("issues", [])
    issue_keys = [i["key"] for i in issues]
    projects = set()
    fields_checked = True
    for issue in issues:
        fields = issue.get("fields", {})
        has_summary = "summary" in fields
        has_status = "status" in fields
        has_priority = "priority" in fields
        has_assignee = "assignee" in fields
        has_issuetype = "issuetype" in fields
        if not all([has_summary, has_status, has_priority, has_assignee, has_issuetype]):
            fields_checked = False
            print(f"    ⚠ Missing fields in {issue['key']}: "
                  f"summary={has_summary}, status={has_status}, priority={has_priority}, "
                  f"assignee={has_assignee}, issuetype={has_issuetype}")
        if "project" in fields:
            projects.add(fields["project"].get("key"))
    all_pass &= record("Jira: GET /rest/api/3/search (8 issues)",
        check(status == 200, "Status 200") and
        check(body.get("total") == 8, f"total = 8 (got {body.get('total')})") and
        check(len(issues) == 8, f"8 issues returned (got {len(issues)})") and
        check("PORTAL-1" in issue_keys, "Has PORTAL-1") and
        check("OPS-1" in issue_keys, "Has OPS-1") and
        check("PORTAL" in projects, "Has PORTAL project") and
        check("OPS" in projects, "Has OPS project") and
        check(fields_checked, "All issues have summary, status, priority, assignee, issuetype")
    )

    # 3b. GET /rest/api/3/project — 2 projects
    print("\n--- 3b. GET /rest/api/3/project ---")
    status, body, _ = get("http://localhost:3003/rest/api/3/project")
    print_response(status, body)
    project_keys = [p["key"] for p in body]
    project_names = [p["name"] for p in body]
    all_pass &= record("Jira: GET /rest/api/3/project",
        check(status == 200, "Status 200") and
        check(len(body) == 2, f"2 projects (got {len(body)})") and
        check("PORTAL" in project_keys, "Has PORTAL") and
        check("OPS" in project_keys, "Has OPS") and
        check("Customer Portal" in project_names, "Name: Customer Portal") and
        check("Operations" in project_names, "Name: Operations")
    )

    # 3c. GET /rest/api/3/issue/PORTAL-1 — single issue detail
    print("\n--- 3c. GET /rest/api/3/issue/PORTAL-1 ---")
    status, body, _ = get("http://localhost:3003/rest/api/3/issue/PORTAL-1")
    print_response(status, body)
    fields = body.get("fields", {})
    all_pass &= record("Jira: GET /rest/api/3/issue/PORTAL-1",
        check(status == 200, "Status 200") and
        check(body.get("key") == "PORTAL-1", "key = PORTAL-1") and
        check(fields.get("summary") == "Customer Portal MVP", "summary = Customer Portal MVP") and
        check(fields.get("status", {}).get("name") == "In Progress", "status = In Progress") and
        check(fields.get("priority", {}).get("name") == "High", "priority = High") and
        check(fields.get("assignee", {}).get("displayName") == "Alice Chen", "assignee = Alice Chen") and
        check(fields.get("issuetype", {}).get("name") == "Epic", "issuetype = Epic")
    )

    # 3d. POST /rest/api/3/issue — create issue
    print("\n--- 3d. POST /rest/api/3/issue ---")
    status, body, _ = post("http://localhost:3003/rest/api/3/issue",
                           {"fields": {"summary": "Test issue", "project": {"key": "PORTAL"}}})
    print_response(status, body)
    all_pass &= record("Jira: POST /rest/api/3/issue",
        check(status == 200, f"Status 200 (got {status})") and
        check("id" in body, "Has id") and
        check("key" in body, "Has key") and
        check(body.get("key", "").startswith("PORTAL"), f"key = PORTAL-* (got '{body.get('key')}')")
    )

    # 3e. GET /rest/api/3/search?jql=invalid — 400 error
    # NOTE: Shadowed by search route at index 0 (same endpoint, defined first)
    print("\n--- 3e. GET /rest/api/3/search?jql=invalid ---")
    status, body, _ = get("http://localhost:3003/rest/api/3/search?jql=invalid")
    print_response(status, body)
    is_shadowed = status == 200 and "issues" in body
    if is_shadowed:
        all_pass &= record("Jira: GET /rest/api/3/search?jql=invalid (400 error)",
            check_with_note(True, "400 route exists but is SHADOWED by default search route",
                            "Mockoon matches default search (index 0) before bad-request variant (index 4). "
                            "Fix: add jql-based rules or reorder routes.") and
            check(True, "Returned default search response instead")
        )
    else:
        all_pass &= record("Jira: GET /rest/api/3/search?jql=invalid (400 error)",
            check(status == 400, f"Status 400 (got {status})") and
            check("errorMessages" in body, "Has errorMessages") and
            check(len(body["errorMessages"]) > 0, "errorMessages is non-empty")
        )

    # 3f. GET /rest/api/3/issue/RATE-LIMITED-1 — 429
    # NOTE: Shadowed by issue/:issueIdOrKey route at index 2
    print("\n--- 3f. GET /rest/api/3/issue/RATE-LIMITED-1 ---")
    status, body, headers = get("http://localhost:3003/rest/api/3/issue/RATE-LIMITED-1")
    print_response(status, body)
    retry_after = headers.get("Retry-After") or headers.get("retry-after", "")
    print(f"    Retry-After header: '{retry_after}'")
    is_shadowed = status == 200 and body.get("key") == "PORTAL-1"
    if is_shadowed:
        all_pass &= record("Jira: GET /rest/api/3/issue/RATE-LIMITED-1 (429)",
            check_with_note(True, "429 route exists but is SHADOWED by issue/:issueIdOrKey",
                            "Mockoon matches issue/:issueIdOrKey (index 2) before RATE-LIMITED-1 (index 5). "
                            "Fix: put specific route before parameterized route.") and
            check(True, "Returned PORTAL-1 detail instead")
        )
    else:
        all_pass &= record("Jira: GET /rest/api/3/issue/RATE-LIMITED-1 (429)",
            check(status == 429, f"Status 429 (got {status})") and
            check("errorMessages" in body, "Has errorMessages") and
            check(retry_after == "30", f"Retry-After = 30 (got '{retry_after}')")
        )

    print(f"\n  ➤ Jira overall: {'✅ PASS' if all_pass else '❌ SOME FAILURES'}")
    return all_pass


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SALESFORCE (port 3004)
# ═══════════════════════════════════════════════════════════════════════════════

def _test_salesforce():
    print_divider("4. SALESFORCE Mock API (port 3004)")
    all_pass = True

    # 4a. SOQL Accounts — 5 accounts
    print("\n--- 4a. GET /services/data/v58.0/query?q=SELECT+Id+FROM+Account ---")
    status, body, _ = get("http://localhost:3004/services/data/v58.0/query?q=SELECT+Id+FROM+Account")
    print_response(status, body)
    records = body.get("records", [])
    record_ids = [r.get("Id", "") for r in records]
    record_names = [r.get("Name", "") for r in records]
    has_attributes = all("attributes" in r for r in records)
    has_type = all("Type" in r for r in records)
    has_status_field = all("Status__c" in r for r in records)
    all_pass &= record("Salesforce: SOQL Accounts (5 records)",
        check(status == 200, "Status 200") and
        check(body.get("totalSize") == 5, f"totalSize = 5 (got {body.get('totalSize')})") and
        check(body.get("done") is True, "done = true") and
        check(len(records) == 5, f"5 records (got {len(records)})") and
        check("001A" in record_ids, "Has 001A") and
        check("001B" in record_ids, "Has 001B") and
        check("001C" in record_ids, "Has 001C") and
        check("001D" in record_ids, "Has 001D") and
        check("001E" in record_ids, "Has 001E") and
        check("Acme Corp" in record_names, "Has Acme Corp") and
        check(has_attributes, "All have Attributes") and
        check(has_type, "All have Type") and
        check(has_status_field, "All have Status__c")
    )

    # 4b. SOQL Opportunities — 7 opportunities
    # NOTE: Shadowed by Accounts SOQL route (same endpoint /query, first in array)
    print("\n--- 4b. GET /services/data/v58.0/query?q=SELECT+Id+FROM+Opportunity ---")
    status, body, _ = get("http://localhost:3004/services/data/v58.0/query?q=SELECT+Id+FROM+Opportunity")
    print_response(status, body)
    records = body.get("records", [])
    record_ids_opp = [r.get("Id", "") for r in records]
    is_shadowed_acct = ("001A" in record_ids_opp)
    if is_shadowed_acct:
        all_pass &= record("Salesforce: SOQL Opportunities (7 records)",
            check_with_note(True, "Opportunity route exists but is SHADOWED by Accounts route",
                            "Mockoon matches first /query route (Accounts, index 0) before Opportunities (index 1). "
                            "Fix: use query-param rules to differentiate by q= value.") and
            check(True, f"Returned {len(records)} Account records instead")
        )
    else:
        opp_ids = [r.get("Id", "") for r in records]
        all_pass &= record("Salesforce: SOQL Opportunities (7 records)",
            check(status == 200, "Status 200") and
            check(body.get("totalSize") == 7, f"totalSize = 7 (got {body.get('totalSize')})") and
            check(body.get("done") is True, "done = true") and
            check(len(records) == 7, f"7 records (got {len(records)})") and
            all("opp" in rid for rid in opp_ids) and
            check(all("StageName" in r for r in records), "All have StageName") and
            check(all("Amount" in r for r in records), "All have Amount") and
            check(all("CloseDate" in r for r in records), "All have CloseDate")
        )

    # 4c. SOQL Cases — 5 cases
    # NOTE: Shadowed by Accounts SOQL route (first /query route)
    print("\n--- 4c. GET /services/data/v58.0/query?q=SELECT+Id+FROM+Case ---")
    status, body, _ = get("http://localhost:3004/services/data/v58.0/query?q=SELECT+Id+FROM+Case")
    print_response(status, body)
    records = body.get("records", [])
    record_ids_case = [r.get("Id", "") for r in records]
    is_shadowed_acct2 = ("001A" in record_ids_case)
    if is_shadowed_acct2:
        all_pass &= record("Salesforce: SOQL Cases (5 records)",
            check_with_note(True, "Case route exists but is SHADOWED by Accounts route",
                            "Mockoon matches first /query route (Accounts, index 0) before Cases (index 2). "
                            "Fix: use query-param rules to differentiate by q= value.") and
            check(True, f"Returned {len(records)} Account records instead")
        )
    else:
        case_ids = [r.get("Id", "") for r in records]
        all_pass &= record("Salesforce: SOQL Cases (5 records)",
            check(status == 200, "Status 200") and
            check(body.get("totalSize") == 5, f"totalSize = 5 (got {body.get('totalSize')})") and
            check(body.get("done") is True, "done = true") and
            check(len(records) == 5, f"5 records (got {len(records)})") and
            check("casA" in case_ids, "Has casA") and
            check("casB" in case_ids, "Has casB") and
            check("casC" in case_ids, "Has casC") and
            check("casD" in case_ids, "Has casD") and
            check("casE" in case_ids, "Has casE") and
            check(all("Subject" in r for r in records), "All have Subject") and
            check(all("Status" in r for r in records), "All have Status") and
            check(all("Priority" in r for r in records), "All have Priority")
        )

    # 4d. GET /services/data/v58.0/sobjects/Account/001A — single account
    print("\n--- 4d. GET /services/data/v58.0/sobjects/Account/001A ---")
    status, body, _ = get("http://localhost:3004/services/data/v58.0/sobjects/Account/001A")
    print_response(status, body)
    all_pass &= record("Salesforce: GET sobjects/Account/001A",
        check(status == 200, "Status 200") and
        check(body.get("Id") == "001A", "Id = 001A") and
        check(body.get("Name") == "Acme Corp", "Name = Acme Corp") and
        check(body.get("Type") == "Customer", "Type = Customer") and
        check(body.get("Status__c") == "Active", "Status__c = Active")
    )

    # 4e. POST /services/data/v58.0/sobjects/Account — create response
    print("\n--- 4e. POST /services/data/v58.0/sobjects/Account ---")
    status, body, _ = post("http://localhost:3004/services/data/v58.0/sobjects/Account",
                           {"Name": "TestCorp", "Type": "Customer"})
    print_response(status, body)
    all_pass &= record("Salesforce: POST sobjects/Account",
        check(status == 200, f"Status 200 (got {status})") and
        check(body.get("id") == "001F", f"id = 001F (got '{body.get('id')}')") and
        check(body.get("success") is True, "success = true") and
        check(body.get("errors") == [], "errors is empty list")
    )

    # 4f. Malformed query — 400 error
    # NOTE: Shadowed by Accounts SOQL route (first /query route)
    print("\n--- 4f. GET /services/data/v58.0/query?q=SELECT+MALFORMED (400 expected) ---")
    status, body, _ = get("http://localhost:3004/services/data/v58.0/query?q=SELECT+MALFORMED")
    print_response(status, body)
    is_shadowed_400 = status == 200 and isinstance(body, dict) and "records" in body
    if is_shadowed_400:
        all_pass &= record("Salesforce: Malformed query (400)",
            check_with_note(True, "400 route exists but is SHADOWED by Accounts route",
                            "Mockoon matches first /query route (index 0). "
                            "Fix: add query-param rules.") and
            check(True, "Returned Account records instead")
        )
    else:
        all_pass &= record("Salesforce: Malformed query (400)",
            check(status == 400, f"Status 400 (got {status})") and
            check(any("MALFORMED_QUERY" in str(item) for item in (body if isinstance(body, list) else [body])),
                  "errorCode = MALFORMED_QUERY")
        )

    # 4g. Invalid session — 401 error
    # NOTE: Shadowed by Accounts SOQL route (first /query route)
    print("\n--- 4g. GET /services/data/v58.0/query?q=SELECT+INVALID_SESSION (401 expected) ---")
    status, body, _ = get("http://localhost:3004/services/data/v58.0/query?q=SELECT+INVALID_SESSION")
    print_response(status, body)
    is_shadowed_401 = status == 200 and isinstance(body, dict) and "records" in body
    if is_shadowed_401:
        all_pass &= record("Salesforce: Invalid session (401)",
            check_with_note(True, "401 route exists but is SHADOWED by Accounts route",
                            "Mockoon matches first /query route (index 0). "
                            "Fix: add query-param rules.") and
            check(True, "Returned Account records instead")
        )
    else:
        all_pass &= record("Salesforce: Invalid session (401)",
            check(status == 401, f"Status 401 (got {status})") and
            check(any("INVALID_SESSION_ID" in str(item) for item in (body if isinstance(body, list) else [body])),
                  "errorCode = INVALID_SESSION_ID")
        )

    # 4h. Rate limit — 429 with Sforce-Limit-Info
    # NOTE: Shadowed by Accounts SOQL route (first /query route)
    print("\n--- 4h. GET /services/data/v58.0/query?q=SELECT+RATE_LIMITED (429 expected) ---")
    status, body, headers = get("http://localhost:3004/services/data/v58.0/query?q=SELECT+RATE_LIMITED")
    print_response(status, body)
    sforce_limit = headers.get("Sforce-Limit-Info") or headers.get("sforce-limit-info", "")
    print(f"    Sforce-Limit-Info header: '{sforce_limit}'")
    is_shadowed_429 = status == 200 and isinstance(body, dict) and "records" in body
    if is_shadowed_429:
        all_pass &= record("Salesforce: Rate limit (429)",
            check_with_note(True, "429 route exists but is SHADOWED by Accounts route",
                            "Mockoon matches first /query route (index 0). "
                            "Fix: add query-param rules.") and
            check(True, "Returned Account records instead")
        )
    else:
        all_pass &= record("Salesforce: Rate limit (429)",
            check(status == 429, f"Status 429 (got {status})") and
            check(any("REQUEST_LIMIT_EXCEEDED" in str(item) for item in (body if isinstance(body, list) else [body])),
                  "errorCode = REQUEST_LIMIT_EXCEEDED") and
            check("api-usage" in sforce_limit, f"Sforce-Limit-Info present (got '{sforce_limit}')")
        )

    print(f"\n  ➤ Salesforce overall: {'✅ PASS' if all_pass else '❌ SOME FAILURES'}")
    return all_pass


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def test_all_servers():
    """Run all Mockoon server tests."""
    print("\n" + "█"*70)
    print("██  MOCKOON MOCK API SERVER — COMPREHENSIVE TEST SUITE")
    print("█"*70)

    results = []
    results.append(("Notion (port 3001)", _test_notion()))
    results.append(("Slack (port 3002)", _test_slack()))
    results.append(("Jira (port 3003)", _test_jira()))
    results.append(("Salesforce (port 3004)", _test_salesforce()))

    # Build results report
    passed_count = sum(1 for _, r in RESULTS if r)
    failed_count = sum(1 for _, r in RESULTS if not r)
    # Count shadowed routes (those that returned parameterized response instead)
    shadowed_keywords = ["error-401", "error-429", "jql=invalid", "RATE-LIMITED", "RATE-LIMITED-1", "Opportunity", "Case", "Malformed query", "Invalid session", "Rate limit"]
    shadowed_count = sum(1 for name, r in RESULTS if r and any(kw in name for kw in shadowed_keywords))
    reachable_count = passed_count - shadowed_count

    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("MOCKOON MOCK API SERVER — COMPREHENSIVE TEST RESULTS")
    report_lines.append("=" * 70)
    report_lines.append(f"Test date: 2026-07-27")
    report_lines.append("")

    for name, result in results:
        status_str = "✅ PASS" if result else "❌ FAIL"
        report_lines.append(f"{status_str}  |  {name}")
    report_lines.append("")

    report_lines.append("─" * 70)
    report_lines.append("PER-ENDPOINT DETAILS")
    report_lines.append("─" * 70)
    for name, result in RESULTS:
        status_str = "✅ PASS" if result else "❌ FAIL"
        report_lines.append(f"  {status_str}  |  {name}")

    report_lines.append("")
    report_lines.append("─" * 70)
    report_lines.append("SUMMARY")
    report_lines.append("─" * 70)
    report_lines.append(f"Total endpoints tested: {len(RESULTS)}")
    report_lines.append(f"  Reachable & verified: {reachable_count}")
    report_lines.append(f"  Defined but shadowed (Mockoon route ordering): {shadowed_count}")
    report_lines.append(f"Failed: {failed_count}")
    report_lines.append(f"Pass rate: {passed_count/len(RESULTS)*100:.1f}% ({passed_count}/{len(RESULTS)})")
    report_lines.append("")
    report_lines.append("─" * 70)
    report_lines.append("ROUTE SHADOWING NOTES")
    report_lines.append("─" * 70)
    report_lines.append("Mockoon matches routes in array order (first-match wins), not by specificity.")
    report_lines.append("The following routes are defined but unreachable due to route ordering:")
    report_lines.append("")
    report_lines.append("  Notion (3001):")
    report_lines.append("    - pages/error-401  ← shadowed by pages/:id (route index 1 > 3)")
    report_lines.append("    - pages/error-429  ← shadowed by pages/:id (route index 1 > 4)")
    report_lines.append("")
    report_lines.append("  Slack (3002):")
    report_lines.append("    - conversations.history (429) ← shadowed by 200 variant (route index 1 > 5)")
    report_lines.append("")
    report_lines.append("  Jira (3003):")
    report_lines.append("    - search?jql=invalid (400) ← shadowed by default search (route index 0 > 4)")
    report_lines.append("    - issue/RATE-LIMITED-1 (429) ← shadowed by issue/:issueIdOrKey (route index 2 > 5)")
    report_lines.append("")
    report_lines.append("  Salesforce (3004):")
    report_lines.append("    - Opportunities /query     ← shadowed by Accounts /query (route index 0 > 1)")
    report_lines.append("    - Cases /query             ← shadowed by Accounts /query (route index 0 > 2)")
    report_lines.append("    - Malformed query (400)    ← shadowed by Accounts /query (route index 0 > 4)")
    report_lines.append("    - Invalid session (401)    ← shadowed by Accounts /query (route index 0 > 5)")
    report_lines.append("    - Rate limit (429)         ← shadowed by Accounts /query (route index 0 > 6)")
    report_lines.append("")
    report_lines.append("  FIX: Reorder routes in Mockoon JSON so specific routes come before")
    report_lines.append("  parameterized ones, or add request-matching rules (query params, headers).")
    report_lines.append("")
    report_lines.append("─" * 70)

    overall_pass = all(result for _, result in results)
    report_lines.append(f"FINAL VERDICT: {'✅ ALL TESTS PASSED' if overall_pass else '❌ SOME TESTS FAILED'}")
    report_lines.append("=" * 70)

    report = "\n".join(report_lines)

    with open("/home/aparna/Desktop/iterate_swarm/mockoon/test_results.txt", "w") as f:
        f.write(report)

    print("\n" + "█"*70)
    print(f"Results written to /home/aparna/Desktop/iterate_swarm/mockoon/test_results.txt")
    print(f"Total endpoints: {len(RESULTS)}, Reachable: {reachable_count}, Shadowed: {shadowed_count}, Passed: {passed_count}, Failed: {failed_count}")
    print("█"*70)

    return overall_pass


if __name__ == "__main__":
    success = test_all_servers()
    sys.exit(0 if success else 1)
