#!/usr/bin/env python3
"""
Fix route shadowing in Mockoon environment JSON files.

Mockoon matches routes in array order (first-match wins). Parameterized routes
like pages/:id shadow specific routes like pages/error-401 that appear later.
"""
import json
import subprocess
import sys
import os

MOCKOON_DIR = "/home/aparna/Desktop/iterate_swarm/mockoon"


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')


def build_rule(target, modifier, value, operator="regex"):
    """Build a Mockoon rule object."""
    return {
        "targets": [
            {
                "target": target,
                "modifier": modifier,
                "value": value
            }
        ],
        "operator": operator
    }


def validate(filepath):
    """Validate a Mockoon file with mockoon-cli."""
    result = subprocess.run(
        ["mockoon-cli", "validate", "-d", filepath],
        capture_output=True, text=True
    )
    return result


# ============================================================
# 1. NOTION (port 3001)
# ============================================================
def fix_notion():
    path = os.path.join(MOCKOON_DIR, "notion.json")
    data = load_json(path)

    routes = data["routes"]
    # Current order: [pages, pages/:id, search, error-401, error-429]
    # New order: [pages, error-401, error-429, pages/:id, search]
    pages = routes[0]       # GET /pages
    pages_id = routes[1]    # GET /pages/:id  (parameterized - shadows 401, 429)
    search = routes[2]      # POST /search
    error_401 = routes[3]   # GET /pages/error-401
    error_429 = routes[4]   # GET /pages/error-429

    data["routes"] = [pages, error_401, error_429, pages_id, search]

    # Reorder rootChildren to match
    rc = data["rootChildren"]
    # Map UUIDs to their objects by looking at which route they reference
    # The rootChildren are in the same order as routes
    rc_map = {
        "2e660c92-7d92-4e94-a358-e498cda19080": rc[0],  # pages
        "40bdb97d-0ed0-4b31-8e38-6ef85eeb71e1": rc[1],  # pages/:id
        "6cdaf6af-41e1-41d9-9e82-3cff14ac17c0": rc[2],  # search
        "943e599d-361e-4bcf-b989-d22e0902795e": rc[3],  # error-401
        "d304519e-b928-4f6c-87d4-99df36f6cd2f": rc[4],  # error-429
    }
    data["rootChildren"] = [
        rc_map["2e660c92-7d92-4e94-a358-e498cda19080"],  # pages
        rc_map["943e599d-361e-4bcf-b989-d22e0902795e"],  # error-401
        rc_map["d304519e-b928-4f6c-87d4-99df36f6cd2f"],  # error-429
        rc_map["40bdb97d-0ed0-4b31-8e38-6ef85eeb71e1"],  # pages/:id
        rc_map["6cdaf6af-41e1-41d9-9e82-3cff14ac17c0"],  # search
    ]

    save_json(path, data)
    print(f"✅ Notion: Reordered routes (error-401, error-429 before pages/:id)")


# ============================================================
# 2. SLACK (port 3002)
# ============================================================
def fix_slack():
    path = os.path.join(MOCKOON_DIR, "slack.json")
    data = load_json(path)

    routes = data["routes"]

    # Find the two conversations.history routes
    conv_history_200 = None
    conv_history_200_idx = None
    conv_history_429 = None
    conv_history_429_idx = None

    for i, r in enumerate(routes):
        if r["endpoint"] == "conversations.history":
            if r["responses"][0]["statusCode"] == "200":
                conv_history_200 = r
                conv_history_200_idx = i
            elif r["responses"][0]["statusCode"] == "429":
                conv_history_429 = r
                conv_history_429_idx = i

    assert conv_history_200 is not None, "Slack: Could not find conversations.history 200"
    assert conv_history_429 is not None, "Slack: Could not find conversations.history 429"

    # Merge the 429 response into the 200 route
    # The 429 response gets a rule: ?trigger=rate_limit
    rate_limit_resp = conv_history_429["responses"][0].copy()
    rate_limit_resp["default"] = False
    rate_limit_resp["rules"] = [
        build_rule("query", "trigger", "rate_limit", "equals")
    ]

    # Ensure the 200 response stays as default
    conv_history_200["responses"][0]["default"] = True
    conv_history_200["responses"][0]["rules"] = []

    # Add the 429 response to the route
    conv_history_200["responses"].append(rate_limit_resp)
    conv_history_200["documentation"] = "Conversation history"

    # Remove the duplicate 429 route
    routes.pop(conv_history_429_idx)
    data["routes"] = routes

    # Update rootChildren: remove the entry for the 429 route
    rc = data["rootChildren"]
    # Find and remove the rootChild UUID matching the 429 route
    # conv_history_429 has uuid 4461f32b-681f-492f-a582-a1d37588f954
    # Its rootChild uuid is 80d925f4-b958-4060-8787-41407d59b9b0
    # Remove by index - rc[5] corresponds to the 429 route
    rc.pop(conv_history_429_idx)
    data["rootChildren"] = rc

    save_json(path, data)
    print(f"✅ Slack: Merged conversations.history routes (200 default, 429 with ?trigger=rate_limit)")


# ============================================================
# 3. JIRA (port 3003)
# ============================================================
def fix_jira():
    path = os.path.join(MOCKOON_DIR, "jira.json")
    data = load_json(path)

    routes = data["routes"]

    # Find search routes
    search_200 = None
    search_200_idx = None
    search_400 = None
    search_400_idx = None

    for i, r in enumerate(routes):
        if r["endpoint"] == "rest/api/3/search":
            if r["responses"][0]["statusCode"] == "200":
                search_200 = r
                search_200_idx = i
            elif r["responses"][0]["statusCode"] == "400":
                search_400 = r
                search_400_idx = i

    assert search_200 is not None, "Jira: Could not find search 200"
    assert search_400 is not None, "Jira: Could not find search 400"

    # Merge 400 response into search route with rule: ?trigger=error
    bad_req_resp = search_400["responses"][0].copy()
    bad_req_resp["default"] = False
    bad_req_resp["rules"] = [
        build_rule("query", "trigger", "error", "equals")
    ]

    # Ensure 200 is default
    search_200["responses"][0]["default"] = True
    search_200["responses"][0]["rules"] = []
    search_200["responses"].append(bad_req_resp)
    search_200["documentation"] = "Search issues"

    # Remove the 400 route
    routes.pop(search_400_idx)
    # After removing search_400 (idx 4), RATE-LIMITED-1 shifts from idx 5 to idx 4

    # Find RATE-LIMITED-1 and issue/:issueIdOrKey
    rate_limited_idx = None
    issue_param_idx = None

    for i, r in enumerate(routes):
        if r["endpoint"] == "rest/api/3/issue/RATE-LIMITED-1":
            rate_limited_idx = i
        elif r["endpoint"] == "rest/api/3/issue/:issueIdOrKey":
            issue_param_idx = i

    assert rate_limited_idx is not None, "Jira: Could not find RATE-LIMITED-1"
    assert issue_param_idx is not None, "Jira: Could not find issue/:issueIdOrKey"

    # Move RATE-LIMITED-1 before issue/:issueIdOrKey
    rate_limited_route = routes.pop(rate_limited_idx)
    # After removal, re-find issue_param_idx if it shifted
    for i, r in enumerate(routes):
        if r["endpoint"] == "rest/api/3/issue/:issueIdOrKey":
            issue_param_idx = i
            break
    routes.insert(issue_param_idx, rate_limited_route)
    data["routes"] = routes

    # Update rootChildren
    rc = data["rootChildren"]
    rc_map = {
        "c1ebc6dd-e974-48cb-83c5-0720f5ef01a8": rc[0],  # search 200
        "70dcfd67-5194-4210-90a2-1ceb86b89d5e": rc[1],  # project
        "bf0a45a5-2c8d-410b-8349-72cd29b4ff0b": rc[2],  # issue/:issueIdOrKey
        "2aacb154-0199-4b85-97f9-c5bf5f15912f": rc[3],  # create issue
        "a276c2f2-5e2b-40d8-95b8-9684d659d879": rc[4],  # search 400 (to remove)
        "55aabdb3-a841-4ef1-9824-fd6cc1737163": rc[5],  # RATE-LIMITED-1
    }

    data["rootChildren"] = [
        rc_map["c1ebc6dd-e974-48cb-83c5-0720f5ef01a8"],  # search merged
        rc_map["70dcfd67-5194-4210-90a2-1ceb86b89d5e"],  # project
        rc_map["55aabdb3-a841-4ef1-9824-fd6cc1737163"],  # RATE-LIMITED-1
        rc_map["bf0a45a5-2c8d-410b-8349-72cd29b4ff0b"],  # issue/:issueIdOrKey
        rc_map["2aacb154-0199-4b85-97f9-c5bf5f15912f"],  # create issue
    ]

    save_json(path, data)
    print(f"✅ Jira: Merged search routes (200 default, 400 with ?trigger=error); moved RATE-LIMITED-1 before :issueIdOrKey")


# ============================================================
# 4. SALESFORCE (port 3004)
# ============================================================
def fix_salesforce():
    path = os.path.join(MOCKOON_DIR, "salesforce.json")
    data = load_json(path)

    routes = data["routes"]

    # Find all GET /services/data/v58.0/query routes
    query_routes = []
    other_routes = []

    for r in routes:
        if r["endpoint"] == "services/data/v58.0/query" and r["method"] == "get":
            query_routes.append(r)
        else:
            other_routes.append(r)

    assert len(query_routes) >= 5, f"Salesforce: Expected at least 5 query routes, got {len(query_routes)}"

    # Build the merged route from the first query route
    merged_route = query_routes[0]
    merged_route["documentation"] = "SOQL Query"

    # Map response body types to their rules
    # Do this BEFORE clearing responses, since query_routes references actual route objects
    response_map = {}

    for r in query_routes:
        label = r["responses"][0]["label"]
        resp = r["responses"][0]
        response_map[label] = resp

    merged_route["responses"] = []

    # Build responses: error responses first (by trigger param), then data queries, then default

    # 400 Malformed query - ?trigger=error (or trigger=400)
    resp_400 = response_map.get("Malformed query", response_map.get("Malformed query"))
    resp_400 = resp_400.copy()
    resp_400["default"] = False
    resp_400["rules"] = [
        build_rule("query", "q", ".*trigger=400")
    ]

    # 401 Auth error - ?trigger=401
    resp_401 = response_map.get("Auth error", response_map.get("Auth error"))
    resp_401 = resp_401.copy()
    resp_401["default"] = False
    resp_401["rules"] = [
        build_rule("query", "q", ".*trigger=401")
    ]

    # 429 Rate limit - ?trigger=429
    resp_429 = response_map.get("Rate limit", response_map.get("Rate limit"))
    resp_429 = resp_429.copy()
    resp_429["default"] = False
    resp_429["rules"] = [
        build_rule("query", "q", ".*trigger=429")
    ]

    # Opportunities - q matches .*FROM Opportunity
    resp_opps = response_map.get("SOQL Opportunities", response_map.get("SOQL Opportunities"))
    resp_opps = resp_opps.copy()
    resp_opps["default"] = False
    resp_opps["rules"] = [
        build_rule("query", "q", ".*FROM Opportunity")
    ]

    # Cases - q matches .*FROM Case
    resp_cases = response_map.get("SOQL Cases", response_map.get("SOQL Cases"))
    resp_cases = resp_cases.copy()
    resp_cases["default"] = False
    resp_cases["rules"] = [
        build_rule("query", "q", ".*FROM Case")
    ]

    # Default: Accounts
    resp_accounts = response_map.get("SOQL Accounts", response_map.get("SOQL Accounts"))
    resp_accounts = resp_accounts.copy()
    resp_accounts["default"] = True
    resp_accounts["rules"] = []

    # Order matters: trigger-based rules first (more specific), then data rules, then default
    merged_route["responses"] = [
        resp_400,
        resp_401,
        resp_429,
        resp_cases,
        resp_opps,
        resp_accounts,
    ]

    # Build new routes: merged query route + other routes
    data["routes"] = [merged_route] + other_routes

    # Update rootChildren: only keep the ones we need
    rc = data["rootChildren"]
    # Map UUIDs to objects
    # Routes at original indices:
    # 0: c9178fd3... (query - Accounts) - keep as merged
    # 1: 4da70feb... (query - Opps) - removed
    # 2: 43d41c05... (query - Cases) - removed
    # 3: bdfff4d8... (sobjects/:objectName/:id) - keep
    # 4: fee59a5d... (sobjects/:objectName) - keep
    # 5: 6017cb5d... (query - 400) - removed
    # 6: 99a0ae79... (query - 401) - removed
    # 7: 3f40da4b... (query - 429) - removed

    rc_map = {
        "a6628ad0-851c-4340-8eb0-6df8bf7bcb1d": rc[0],  # query merged
        "3684b921-c7e0-4f42-941b-62763b67ff7b": rc[3],  # sobjects/:objectName/:id
        "ec35b466-7201-47ab-918c-13f41f817dd6": rc[4],  # sobjects/:objectName
        # The others are removed
    }

    data["rootChildren"] = [
        rc_map["a6628ad0-851c-4340-8eb0-6df8bf7bcb1d"],  # query merged
        rc_map["3684b921-c7e0-4f42-941b-62763b67ff7b"],  # sobjects/:objectName/:id
        rc_map["ec35b466-7201-47ab-918c-13f41f817dd6"],  # sobjects/:objectName
    ]

    save_json(path, data)
    print(f"✅ Salesforce: Merged 5 /query routes into 1 route with 6 rule-based responses")


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("Fixing Mockoon route shadowing issues")
    print("=" * 60)

    # Fix all four files
    fix_notion()
    fix_slack()
    fix_jira()
    fix_salesforce()

    print("\n" + "=" * 60)
    print("Validating all files with mockoon-cli")
    print("=" * 60)

    files = ["notion.json", "slack.json", "jira.json", "salesforce.json"]
    all_valid = True

    for fname in files:
        filepath = os.path.join(MOCKOON_DIR, fname)
        result = validate(filepath)
        if result.returncode == 0:
            print(f"✅ {fname}: VALID")
        else:
            all_valid = False
            print(f"❌ {fname}: INVALID")
            print(result.stdout)
            print(result.stderr)

    if all_valid:
        print("\n✅ All files validated successfully!")
        return 0
    else:
        print("\n❌ Some files failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
