#!/usr/bin/env python3
"""
Captcha Provider Quick-Switch CLI
=================================

Quickly compare and switch between captcha solving providers without
running the full registration flow. Useful for:
  - Comparing costs before committing to one provider
  - Testing that your API key works
  - Seeing which providers support free trials

Usage:
  python switch_captcha.py list                  # List all providers
  python switch_captcha.py info capsolver       # Show details for one provider
  python switch_captcha.py balance capsolver     # Check account balance (needs API key)
  python switch_captcha.py test capsolver        # Test createTask + getTaskResult

Environment:
  CAPSOLVER_API_KEY, ANTICAPTCHA_API_KEY, CAPMONSTER_API_KEY, TWOCAPTCHA_API_KEY
  Or generic: CAPTCHA_API_KEY
"""

import os
import sys
import time
import json
import argparse
import requests

# ─── Provider configs (kept in sync with batch_tempmail.py) ──────────────────
PROVIDERS = {
    "2captcha": {
        "name": "2Captcha",
        "create": "https://api.2captcha.com/createTask",
        "result": "https://api.2captcha.com/getTaskResult",
        "balance": "https://api.2captcha.com/getBalance",
        "signup": "https://2captcha.com",
        "env_var": "TWOCAPTCHA_API_KEY",
        "free_credit": "None",
        "cost_per_solve": "$0.003",
        "avg_solve_time": "20-40s",
        "notes": "Industry standard, most reliable",
    },
    "capsolver": {
        "name": "CapSolver",
        "create": "https://api.capsolver.com/createTask",
        "result": "https://api.capsolver.com/getTaskResult",
        "balance": "https://api.capsolver.com/getBalance",
        "signup": "https://dashboard.capsolver.com/signup?invite=U5fbvdAh-zXv",
        "env_var": "CAPSOLVER_API_KEY",
        "free_credit": "$1 (no payment method)",
        "cost_per_solve": "$0.0015",
        "avg_solve_time": "15-30s",
        "notes": "Cheapest + has $1 free trial",
    },
    "anticaptcha": {
        "name": "Anti-Captcha",
        "create": "https://api.anti-captcha.com/createTask",
        "result": "https://api.anti-captcha.com/getTaskResult",
        "balance": "https://api.anti-captcha.com/getBalance",
        "signup": "https://anti-captcha.com",
        "env_var": "ANTICAPTCHA_API_KEY",
        "free_credit": "$5 (phone verify)",
        "cost_per_solve": "$0.002",
        "avg_solve_time": "25-45s",
        "notes": "Mature service, requires phone verification for free credit",
    },
    "capmonster": {
        "name": "CapMonster Cloud",
        "create": "https://api.capmonster.cloud/createTask",
        "result": "https://api.capmonster.cloud/getTaskResult",
        "balance": "https://api.capmonster.cloud/getBalance",
        "signup": "https://capmonster.cloud",
        "env_var": "CAPMONSTER_API_KEY",
        "free_credit": "Refundable $5 trial",
        "cost_per_solve": "$0.0015",
        "avg_solve_time": "15-30s",
        "notes": "Refundable trial — top up $5 then request refund",
    },
}


class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    CYAN = "\033[96m"; GREEN = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"
    BLUE = "\033[94m"; MAGENTA = "\033[95m"


def get_api_key(name: str) -> str:
    """Look up API key from provider-specific or generic env var."""
    info = PROVIDERS.get(name)
    if not info:
        return ""
    # Try provider-specific first, then generic CAPTCHA_API_KEY
    return os.getenv(info["env_var"]) or os.getenv("CAPTCHA_API_KEY") or os.getenv("TWOCAPTCHA_API_KEY", "")


def cmd_list(_args):
    """List all available captcha providers."""
    print(f"\n{C.BOLD}{C.CYAN}Available Captcha Providers{C.RESET}")
    print(f"{C.BOLD}{'─' * 80}{C.RESET}")
    print(f"{'Name':<10}  {'Cost/solve':<12}  {'Free Credit':<30}  {'Avg Time':<12}")
    print(f"{'─' * 80}")
    for key, info in PROVIDERS.items():
        free = info["free_credit"]
        # Color the free credit if it exists
        if free != "None":
            free_display = f"{C.GREEN}{free}{C.RESET}"
        else:
            free_display = free
        print(f"{info['name']:<10}  {info['cost_per_solve']:<12}  {free_display:<30}  {info['avg_solve_time']:<12}")
    print(f"\n{C.DIM}Use 'python switch_captcha.py info <name>' for details.{C.RESET}\n")


def cmd_info(args):
    """Show detailed info about one provider."""
    key = args.provider.lower()
    if key not in PROVIDERS:
        print(f"{C.RED}✗ Unknown provider: {args.provider}{C.RESET}")
        print(f"  Available: {', '.join(PROVIDERS.keys())}")
        sys.exit(1)
    info = PROVIDERS[key]
    print(f"\n{C.BOLD}{C.CYAN}{info['name']}{C.RESET}")
    print(f"{C.BOLD}{'─' * 60}{C.RESET}")
    for k, v in info.items():
        print(f"  {C.BOLD}{k}{C.RESET}: {v}")
    print()
    # Show API key status
    api_key = get_api_key(key)
    if api_key:
        masked = api_key[:4] + "***" + api_key[-4:] if len(api_key) > 8 else "***"
        print(f"  {C.GREEN}✓ API key found in env: {masked}{C.RESET}")
    else:
        print(f"  {C.YELLOW}✗ No API key found. Set {info['env_var']} or CAPTCHA_API_KEY env var.{C.RESET}")
        print(f"  {C.DIM}  Sign up: {info['signup']}{C.RESET}")
    print()


def cmd_balance(args):
    """Check account balance via provider's getBalance endpoint."""
    key = args.provider.lower()
    if key not in PROVIDERS:
        print(f"{C.RED}✗ Unknown provider: {args.provider}{C.RESET}")
        sys.exit(1)

    info = PROVIDERS[key]
    api_key = get_api_key(key)
    if not api_key:
        print(f"{C.RED}✗ No API key found for {info['name']}.{C.RESET}")
        print(f"  Set {info['env_var']} or CAPTCHA_API_KEY env var.")
        sys.exit(1)

    print(f"{C.CYAN}[*]{C.RESET} Checking balance on {info['name']}...")
    try:
        resp = requests.post(
            info["balance"],
            json={"clientKey": api_key},
            timeout=10,
        )
        data = resp.json()
        if "balance" in data:
            balance = data["balance"]
            print(f"{C.GREEN}✓{C.RESET} Balance: ${balance:.4f}")
            # Estimate
            cost = float(info["cost_per_solve"].replace("$", ""))
            solves = int(balance / cost) if cost > 0 else 0
            print(f"  → ~{solves} solves remaining (at {info['cost_per_solve']}/solve)")
        elif "errorId" in data and data["errorId"] != 0:
            print(f"{C.RED}✗ API error: {data.get('errorDescription', data)}{C.RESET}")
        else:
            print(f"{C.YELLOW}?{C.RESET} Unexpected response: {data}")
    except Exception as e:
        print(f"{C.RED}✗ Request failed: {e}{C.RESET}")


def cmd_test(args):
    """Test createTask + getTaskResult against a dummy reCAPTCHA."""
    key = args.provider.lower()
    if key not in PROVIDERS:
        print(f"{C.RED}✗ Unknown provider: {args.provider}{C.RESET}")
        sys.exit(1)

    info = PROVIDERS[key]
    api_key = get_api_key(key)
    if not api_key:
        print(f"{C.RED}✗ No API key found for {info['name']}.{C.RESET}")
        print(f"  Set {info['env_var']} or CAPTCHA_API_KEY env var.")
        sys.exit(1)

    print(f"{C.CYAN}[*]{C.RESET} Testing {info['name']} (this will consume 1 solve credit)...")
    print(f"  Endpoint: {info['create']}")

    # Use the real Xiaomi register URL + real site key — this is a REAL solve test
    # Use a dummy e_token (Xiaomi will reject it, but captcha provider will still charge)
    body = {
        "clientKey": api_key,
        "task": {
            "type": "RecaptchaV2EnterpriseTaskProxyless",
            "websiteURL": "https://global.account.xiaomi.com/fe/service/register?_locale=en_US&_uRegion=ID",
            "websiteKey": "6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4",
            "enterprisePayload": {"s": "test_e_token_abcdef123456"},
        },
    }

    try:
        # Create task
        t0 = time.time()
        resp = requests.post(info["create"], json=body, timeout=15)
        result = resp.json()
        elapsed_create = time.time() - t0

        if result.get("errorId", 0) != 0:
            print(f"{C.RED}✗ createTask failed: {result}{C.RESET}")
            return

        task_id = result["taskId"]
        print(f"  {C.GREEN}✓{C.RESET} Task created in {elapsed_create:.2f}s: {task_id}")

        # Poll for result
        print(f"  {C.CYAN}[*]{C.RESET} Polling for solution...")
        for attempt in range(30):
            time.sleep(3)
            poll_body = {"clientKey": api_key, "taskId": task_id}
            poll_resp = requests.post(info["result"], json=poll_body, timeout=15)
            poll_result = poll_resp.json()

            if poll_result.get("status") == "ready":
                elapsed_total = time.time() - t0
                print(f"  {C.GREEN}✓{C.RESET} Solved in {elapsed_total:.1f}s")
                token = poll_result["solution"]["gRecaptchaResponse"]
                print(f"  Token: {token[:60]}...")
                print(f"\n{C.GREEN}✓ {info['name']} is working! You can use it with batch_tempmail.py{C.RESET}")
                print(f"  python batch_tempmail.py -c {key} --count 10")
                return
            elif poll_result.get("errorId", 0) != 0:
                print(f"  {C.RED}✗ Solve error: {poll_result}{C.RESET}")
                return

        print(f"  {C.YELLOW}⏱ Timeout after 90s — provider may be slow or unreachable{C.RESET}")
    except Exception as e:
        print(f"{C.RED}✗ Test failed: {e}{C.RESET}")


def cmd_compare(_args):
    """Side-by-side comparison of all providers."""
    print(f"\n{C.BOLD}{C.CYAN}Captcha Provider Comparison{C.RESET}")
    print(f"{C.BOLD}{'─' * 100}{C.RESET}")
    header = f"{'Provider':<18}  {'Cost/solve':<11}  {'10 acc':<8}  {'100 acc':<9}  {'Free Credit':<25}"
    print(header)
    print(f"{'─' * 100}")
    for key, info in PROVIDERS.items():
        cost = float(info["cost_per_solve"].replace("$", ""))
        cost_10 = cost * 10 * 2  # 2 retries avg
        cost_100 = cost * 100 * 2
        free = info["free_credit"]
        if free != "None":
            free_d = f"{C.GREEN}{free}{C.RESET}"
        else:
            free_d = free
        print(f"{info['name']:<18}  {info['cost_per_solve']:<11}  ${cost_10:<7.2f}  ${cost_100:<8.2f}  {free_d:<25}")
    print(f"\n{C.DIM}* Costs assume 2 retries per account (realistic average){C.RESET}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Quick-switch between captcha solving providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                     # List all providers
  %(prog)s info capsolver           # Show capsolver details
  %(prog)s balance capsolver        # Check balance (needs CAPSOLVER_API_KEY env)
  %(prog)s test capsolver           # Test createTask + getTaskResult
  %(prog)s compare                  # Side-by-side cost comparison
        """
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all providers")
    sub.add_parser("compare", help="Side-by-side cost comparison")

    p_info = sub.add_parser("info", help="Show details for one provider")
    p_info.add_argument("provider", help="Provider name (2captcha, capsolver, anticaptcha, capmonster)")

    p_bal = sub.add_parser("balance", help="Check account balance")
    p_bal.add_argument("provider", help="Provider name")

    p_test = sub.add_parser("test", help="Test createTask + getTaskResult (costs 1 solve)")
    p_test.add_argument("provider", help="Provider name")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    cmd_map = {
        "list": cmd_list,
        "info": cmd_info,
        "balance": cmd_balance,
        "test": cmd_test,
        "compare": cmd_compare,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()