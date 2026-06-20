#!/usr/bin/env python3
"""
Xiaomi Account Batch Registration — Temp Mail Edition
=====================================================

Modified from guajiimi/xiaomi-register to use mail.tm instead of Gmail IMAP.
Registers N Xiaomi accounts in batch with one mail.tm inbox per account.

Usage:
    python batch_tempmail.py                  # register 10 accounts (default)
    python batch_tempmail.py --count 25       # register 25 accounts
    python batch_tempmail.py --resume         # skip already-registered emails
    python batch_tempmail.py --start-from 5   # start from index 5

Prerequisites:
    - Python 3.10+
    - Node.js 18+ (for scripts/encrypt.cjs EUI encryption)
    - pip install curl-cffi pycryptodome python-dotenv mailtm requests

Environment (.env):
    TWOCAPTCHA_API_KEY=your_2captcha_key
    MAILTM_PASSWORD_BASE=SomeRandomPass123!  # same password reused for all mail.tm inboxes

Output:
    accounts.jsonl  — one JSON per line for each SUCCESS
    failed.jsonl    — one JSON per line for each FAILURE (with error reason)
"""

import os
import sys
import json
import time
import uuid
import random
import string
import argparse
import re
import base64
import subprocess
from pathlib import Path
from urllib.parse import urlencode, quote, urlparse, parse_qs

from dotenv import load_dotenv
from curl_cffi import requests as cffi_requests
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Util.Padding import pad

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PAYLOAD_TEMPLATE = SCRIPT_DIR / "docs" / "payload_template.json"
ENCRYPT_CJS = SCRIPT_DIR / "scripts" / "encrypt.cjs"
OUTPUT_SUCCESS = SCRIPT_DIR / "accounts.jsonl"
OUTPUT_FAILED = SCRIPT_DIR / "failed.jsonl"

# ─── Constants ────────────────────────────────────────────────────────────────
CAPTCHA_SITE_KEY = "6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4"
CAPTCHA_PARAM_K = "8027422fb0eb42fbac1b521ec4a7961f"
REGISTER_URL = "https://global.account.xiaomi.com/fe/service/register?_locale=en_US&_uRegion=ID"
MAILTM_BASE = "https://api.mail.tm"
TWOCAPTCHA_CREATE = "https://api.2captcha.com/createTask"
TWOCAPTCHA_RESULT = "https://api.2captcha.com/getTaskResult"

CAPTCHA_RSA_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArxfNLkuAQ/BYHzkzVwtu
g+0abmYRBVCEScSzGxJIOsfxVzcuqaKO87H2o2wBcacD3bRHhMjTkhSEqxPjQ/FE
XuJ1cdbmr3+b3EQR6wf/cYcMx2468/QyVoQ7BADLSPecQhtgGOllkC+cLYN6Md34
Uii6U+VJf0p0q/saxUTZvhR2ka9fqJ4+6C6cOghIecjMYQNHIaNW+eSKunfFsXVU
+QfMD0q2EM9wo20aLnos24yDzRjh9HJc6xfr37jRlv1/boG/EABMG9FnTm35xWrV
R0nw3cpYF7GZg13QicS/ZwEsSd4HyboAruMxJBPvK3Jdr4ZS23bpN0cavWOJsBqZ
VwIDAQAB
-----END PUBLIC KEY-----"""

EUI_RSA_PEM = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYEVrK/4Mahiv0pUJgTybx4J9P
5dUT/Y0PuwMbk+gMU+jrZnBiXGv6/hCH1avIhoBcE535F8nJQQN3UavZdFkYidso
XuEnat3+eVTp3FslyhRwIBDF09v4vDhRtxFOT+R7uH7h/mzmyA2/+lfIMWGIrffX
prYizbV76+YQKhoqFQIDAQAB
-----END PUBLIC KEY-----"""

AES_IV = b"0102030405060708"
KEY_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"

# Xiaomi password requirements: 8-16 chars, mix of letters/digits/symbols
def generate_xiaomi_password() -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(chars, k=12))

# ─── Console helpers ──────────────────────────────────────────────────────────
class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    RED = "\033[91m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
    BLUE = "\033[94m"; MAGENTA = "\033[95m"; CYAN = "\033[96m"

def info(m): print(f"{C.CYAN}[*]{C.RESET} {m}")
def ok(m):   print(f"{C.GREEN}[✓]{C.RESET} {m}")
def warn(m): print(f"{C.YELLOW}[!]{C.RESET} {m}")
def err(m):  print(f"{C.RED}[✗]{C.RESET} {m}")
def step(m): print(f"\n{C.MAGENTA}{C.BOLD}▸ {m}{C.RESET}")

# ─── Crypto ───────────────────────────────────────────────────────────────────
def random_aes_key(length=16):
    return "".join(random.choices(KEY_CHARS, k=length))

def aes_encrypt(plaintext: str, aes_key: str) -> str:
    cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_CBC, AES_IV)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct).decode("utf-8")

def rsa_encrypt(data_b64: str, pem: str) -> str:
    key = RSA.import_key(pem)
    cipher = PKCS1_v1_5.new(key)
    ct = cipher.encrypt(data_b64.encode("utf-8"))
    return base64.b64encode(ct).decode("utf-8")

def encrypt_captcha_payload(payload: dict) -> tuple:
    aes_key = random_aes_key()
    payload_json = json.dumps(payload, separators=(",", ":"))
    d = aes_encrypt(payload_json, aes_key)
    s = rsa_encrypt(base64.b64encode(aes_key.encode()).decode(), CAPTCHA_RSA_PEM)
    return s, d

def build_eui(fields: dict) -> tuple:
    """Call Node.js encrypt.cjs to compute EUI + encrypted params."""
    if not ENCRYPT_CJS.exists():
        raise RuntimeError(f"encrypt.cjs not found at {ENCRYPT_CJS}")
    result = subprocess.run(
        ["node", str(ENCRYPT_CJS), json.dumps(fields)],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        raise RuntimeError(f"encrypt.cjs failed: {result.stderr.strip()}")
    out = json.loads(result.stdout)
    return out["EUI"], out["encryptedParams"]

# ─── mail.tm client ───────────────────────────────────────────────────────────
class TempMail:
    """Wrapper around mail.tm API for one disposable inbox.

    Note: mail.tm's anti-bot returns XML when curl_cffi's Chrome TLS fingerprint
    is used. We use a plain session here (no impersonation).
    """
    def __init__(self, password: str):
        self.password = password
        self.address = None
        self.account_id = None
        self.token = None
        self.session = cffi_requests.Session()  # NO impersonate for mail.tm

    def _request_with_retry(self, method: str, url: str, max_retries: int = 3, **kwargs):
        """mail.tm has aggressive rate limits — wrap with retry + backoff."""
        last_err = None
        for attempt in range(max_retries):
            try:
                if method == "GET":
                    r = self.session.get(url, **kwargs)
                elif method == "POST":
                    r = self.session.post(url, **kwargs)
                elif method == "DELETE":
                    r = self.session.delete(url, **kwargs)
                else:
                    raise ValueError(f"Unknown method: {method}")
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 10)) + random.randint(2, 5)
                    warn(f"mail.tm rate limited (429), waiting {wait}s...")
                    time.sleep(wait)
                    continue
                return r
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"mail.tm {method} {url} failed after {max_retries} retries: {last_err}")

    def _get_domain(self) -> str:
        # Don't set Accept header — mail.tm returns JSON-LD (dict) if Accept=json,
        # or simple list if no Accept. We handle both.
        r = self._request_with_retry("GET", f"{MAILTM_BASE}/domains", timeout=15)
        data = r.json()
        # Normalize: might be list or {"hydra:member": [...]}
        if isinstance(data, dict):
            domains = data.get("hydra:member", [])
        else:
            domains = data
        if not domains:
            raise RuntimeError("No mail.tm domains available")
        # Pick first active domain
        for d in domains:
            if isinstance(d, dict) and d.get("isActive"):
                return d["domain"]
        # Fallback to first
        first = domains[0]
        if isinstance(first, dict):
            return first["domain"]
        raise RuntimeError(f"Unexpected domain format: {first}")

    def create(self, local_prefix: str = "mx") -> str:
        domain = self._get_domain()
        if local_prefix == "mx":
            local_prefix = "mx" + ''.join(random.choices(string.digits + string.ascii_lowercase, k=10))
        self.address = f"{local_prefix}@{domain}"
        # Create account with retry
        r = self._request_with_retry(
            "POST", f"{MAILTM_BASE}/accounts", timeout=15,
            json={"address": self.address, "password": self.password}
        )
        if r.status_code >= 400:
            raise RuntimeError(f"mail.tm account create failed: {r.status_code} {r.text[:200]}")
        self.account_id = r.json()["id"]
        # Get token
        self._refresh_token()
        return self.address

    def _refresh_token(self):
        r = self._request_with_retry(
            "POST", f"{MAILTM_BASE}/token", timeout=15,
            json={"address": self.address, "password": self.password}
        )
        if r.status_code >= 400:
            raise RuntimeError(f"mail.tm token failed: {r.status_code} {r.text[:200]}")
        self.token = r.json()["token"]

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def get_messages(self):
        r = self._request_with_retry("GET", f"{MAILTM_BASE}/messages", timeout=15,
                                     headers=self._headers())
        if r.status_code != 200:
            return []
        data = r.json()
        # Handle both list and JSON-LD hydra format
        if isinstance(data, dict):
            return data.get("hydra:member", [])
        return data if isinstance(data, list) else []

    def get_message_source(self, msg_id: str) -> str:
        """Get full message body (HTML or text)."""
        r = self._request_with_retry(
            "GET", f"{MAILTM_BASE}/messages/{msg_id}", timeout=15,
            headers=self._headers()
        )
        if r.status_code != 200:
            return ""
        data = r.json()
        # mail.tm returns intro, text, html fields
        return " ".join(filter(None, [data.get("intro", ""), data.get("text", ""), data.get("html", "")]))

    def delete(self):
        """Best-effort cleanup."""
        try:
            if self.account_id:
                self._request_with_retry(
                    "DELETE", f"{MAILTM_BASE}/accounts/{self.account_id}", timeout=10,
                    headers=self._headers()
                )
        except Exception:
            pass

def poll_verification_code(tm: TempMail, timeout: int = 180) -> str:
    """Poll mail.tm inbox until 6-digit code from Xiaomi appears."""
    deadline = time.time() + timeout
    seen_ids = set()
    info(f"Polling {tm.address} for code (timeout {timeout}s)...")

    while time.time() < deadline:
        try:
            msgs = tm.get_messages()
            for m in msgs:
                msg_id = m.get("id")
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
                frm = (m.get("from", {}) or {}).get("address", "")
                subj = m.get("subject", "")
                if "xiaomi" in frm.lower() or "xiaomi" in subj.lower() or "notice" in frm.lower():
                    body = tm.get_message_source(msg_id)
                    body = body.replace("=\r\n", "").replace("=\n", "")
                    match = re.search(r"verification code is[:\s]*(\d{6})", body, re.IGNORECASE)
                    if match:
                        code = match.group(1)
                        ok(f"Code received: {code}")
                        return code
        except Exception as e:
            warn(f"mail.tm poll error: {e}")
            try:
                tm._refresh_token()
            except Exception:
                pass
        time.sleep(5)

    raise TimeoutError(f"No code received within {timeout}s for {tm.address}")

# ─── Registration flow ────────────────────────────────────────────────────────
def make_session() -> cffi_requests.Session:
    """Build session — proxy optional (set HTTP_PROXY env var if needed)."""
    proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if proxy:
        # curl_cffi uses singular 'proxy' param
        return cffi_requests.Session(impersonate="chrome124", proxy=proxy)
    return cffi_requests.Session(impersonate="chrome124")

def load_payload_template() -> dict:
    with open(PAYLOAD_TEMPLATE) as f:
        return json.load(f)

def step2_captcha_data(session, tm: TempMail):
    """POST captcha/v2/data, returns e_token."""
    payload = load_payload_template()
    now_ms = int(time.time() * 1000)
    payload["startTs"] = now_ms
    payload["endTs"] = now_ms + random.randint(500, 1500)
    payload["env"]["p11"] = now_ms
    payload["nonce"]["t"] = int(now_ms / 1000)
    payload["nonce"]["r"] = random.randint(1000000000, 9999999999)
    payload["env"]["p33"] = []
    s, d = encrypt_captcha_payload(payload)

    ts = int(time.time() * 1000)
    url = f"https://verify.sec.xiaomi.com/captcha/v2/data?k={CAPTCHA_PARAM_K}&locale=en_US&_t={ts}"
    resp = session.post(url, data=f"s={quote(s)}&d={quote(d)}&a=register",
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"captcha/v2/data failed: {data}")
    e_token = parse_qs(urlparse(data["data"]["url"]).query)["e"][0]
    return e_token

def step3_solve_captcha(session, e_token: str, api_key: str) -> str:
    create_body = {
        "clientKey": api_key,
        "task": {
            "type": "RecaptchaV2EnterpriseTaskProxyless",
            "websiteURL": REGISTER_URL,
            "websiteKey": CAPTCHA_SITE_KEY,
            "enterprisePayload": {"s": e_token}
        }
    }
    resp = session.post(TWOCAPTCHA_CREATE, json=create_body)
    result = resp.json()
    if result.get("errorId", 0) != 0:
        raise RuntimeError(f"2Captcha createTask error: {result}")
    task_id = result["taskId"]
    info(f"2Captcha task: {task_id}")

    for attempt in range(60):
        time.sleep(5)
        poll_body = {"clientKey": api_key, "taskId": task_id}
        resp = session.post(TWOCAPTCHA_RESULT, json=poll_body)
        result = resp.json()
        if result.get("status") == "ready":
            return result["solution"]["gRecaptchaResponse"]
        if result.get("errorId", 0) != 0:
            raise RuntimeError(f"2Captcha error: {result}")
    raise TimeoutError("2Captcha timed out after 300s")

def step4_recaptcha_verify(session, e_token: str, g_recaptcha: str) -> str:
    ts = int(time.time() * 1000)
    url = f"https://verify.sec.xiaomi.com/captcha/v2/recaptcha/verify?k={CAPTCHA_PARAM_K}&locale=en_US&_t={ts}"
    resp = session.post(url, data=f"e={quote(e_token)}&g={quote(g_recaptcha)}&type=4",
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = resp.json()
    if data.get("code") != 0 or not data.get("data", {}).get("result"):
        raise RuntimeError(f"recaptcha verify failed: {data}")
    return data["data"]["token"]

def step6_send_reg_ticket(session, vtoken: str, eui: str, enc_email: str, enc_password: str):
    device_id = f"wb_{uuid.uuid4()}"
    url = "https://global.account.xiaomi.com/pass/sendEmailRegTicket"
    headers = {
        "eui": eui,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": REGISTER_URL,
        "Origin": "https://global.account.xiaomi.com",
    }
    session.cookies.set("vToken", vtoken, domain="global.account.xiaomi.com")
    session.cookies.set("vAction", "register", domain="global.account.xiaomi.com")
    session.cookies.set("deviceId", device_id, domain="global.account.xiaomi.com")
    body = urlencode({
        "email": enc_email, "password": enc_password,
        "region": "ID", "sid": "", "icode": "",
    })
    resp = session.post(url, data=body, headers=headers)
    text = resp.text
    if text.startswith("&&&START&&&"):
        text = text[len("&&&START&&&"):]
    data = json.loads(text)
    if data.get("code") != 0:
        raise RuntimeError(f"sendEmailRegTicket failed: {data}")
    return data

def step8_verify_reg_ticket(session, email: str, password: str, code: str) -> dict:
    eui, enc_params = build_eui({"email": email, "password": password})
    enc_email = enc_params["email"]
    enc_password = enc_params["password"]
    device_fp = "".join(random.choices("0123456789abcdef", k=32))
    url = "https://global.account.xiaomi.com/pass/verifyEmailRegTicket"
    headers = {
        "eui": eui,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    body = (
        f"ticket={code}&region=ID&email={quote(enc_email, safe='')}"
        f"&env=web&qs=%253Fsid%253Dpassport&isAcceptLicense=true"
        f"&sid=&password={quote(enc_password, safe='')}"
        f"&policyName=globalmiaccount&callback=&deviceFingerprint={device_fp}"
    )
    resp = session.post(url, data=body, headers=headers)
    text = resp.text
    if text.startswith("&&&START&&&"):
        text = text[len("&&&START&&&"):]
    data = json.loads(text)
    if data.get("code") != 0:
        raise RuntimeError(f"verifyEmailRegTicket failed: {data}")
    return data

def register_one(idx: int, total: int, api_key: str, mailtm_password: str) -> dict:
    """Register one account. Returns dict with status, email, password, error."""
    print(f"\n{C.BOLD}{C.CYAN}{'═'*60}")
    print(f"  Account {idx+1}/{total}")
    print(f"{'═'*60}{C.RESET}")

    # Setup temp mail
    tm = TempMail(password=mailtm_password)
    try:
        address = tm.create()
        info(f"mail.tm inbox: {address}")
    except Exception as e:
        err(f"mail.tm setup failed: {e}")
        return {"status": "failed", "stage": "tempmail_setup", "error": str(e)}

    password = generate_xiaomi_password()
    session = make_session()
    vtoken: str = ""

    try:
        # Warm-up
        session.get(REGISTER_URL)

        # Captcha loop with retry
        for attempt in range(4):
            try:
                e_token = step2_captcha_data(session, tm)
                g = step3_solve_captcha(session, e_token, api_key)
                vtoken = step4_recaptcha_verify(session, e_token, g)
                ok(f"Captcha pass (attempt {attempt+1})")
                break
            except RuntimeError as e:
                warn(f"Captcha attempt {attempt+1} failed: {e}")
                if attempt == 3:
                    raise
                time.sleep(3)

        # Encrypt credentials
        eui, enc_params = build_eui({"email": address, "password": password})
        enc_email = enc_params["email"]
        enc_password = enc_params["password"]

        # Send registration ticket
        step6_send_reg_ticket(session, vtoken, eui, enc_email, enc_password)
        ok("Registration ticket sent — waiting for code...")

        # Poll mail.tm for verification code
        code = poll_verification_code(tm, timeout=180)

        # Final verification → create account
        step8_verify_reg_ticket(session, address, password, code)
        ok(f"Account created: {address}")

        # Extract session cookies
        cookies = {}
        for name in ("passToken", "serviceToken", "cUserId", "userId"):
            val = session.cookies.get(name, domain="account.xiaomi.com") or session.cookies.get(name)
            if val:
                cookies[name] = val

        return {
            "status": "success",
            "email": address,
            "password": password,
            "cookies": cookies,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    except Exception as e:
        err(f"Registration failed: {e}")
        return {
            "status": "failed",
            "email": address,
            "password": password,
            "stage": "registration",
            "error": str(e),
            "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    finally:
        # Optionally delete mail.tm inbox to keep things clean
        # tm.delete()
        pass

def load_existing_emails() -> set:
    """For resume mode — return set of already-registered emails."""
    emails = set()
    if OUTPUT_SUCCESS.exists():
        with open(OUTPUT_SUCCESS) as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                    if rec.get("email"):
                        emails.add(rec["email"])
                except Exception:
                    pass
    return emails

def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--resume", action="store_true", help="Skip already-registered emails")
    parser.add_argument("--start-from", type=int, default=0, help="Start from 1-based index")
    parser.add_argument("--sleep", type=int, default=15, help="Seconds between accounts")
    args = parser.parse_args()

    api_key = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
    mailtm_password = os.getenv("MAILTM_PASSWORD_BASE", "MxBatchPass2026!")

    if not api_key:
        err("TWOCAPTCHA_API_KEY not set in .env")
        sys.exit(1)

    print(f"{C.BOLD}{C.MAGENTA}")
    print("┌──────────────────────────────────────────────┐")
    print("│  Xiaomi Batch Register — mail.tm Edition     │")
    print(f"│  Target: {args.count} accounts                       │")
    print("└──────────────────────────────────────────────┘")
    print(f"{C.RESET}")

    skip = set()
    if args.resume:
        skip = load_existing_emails()
        if skip:
            info(f"Resume: skipping {len(skip)} already-registered emails")

    successes, failures = 0, 0
    started = time.time()

    for i in range(args.count):
        if i < args.start_from - 1:
            continue

        result = register_one(i, args.count, api_key, mailtm_password)

        # Persist immediately
        out = OUTPUT_SUCCESS if result["status"] == "success" else OUTPUT_FAILED
        with open(out, "a") as f:
            f.write(json.dumps(result) + "\n")

        if result["status"] == "success":
            successes += 1
        else:
            failures += 1

        if i < args.count - 1:
            print(f"\n{C.DIM}Sleeping {args.sleep}s before next account...{C.RESET}")
            time.sleep(args.sleep)

    elapsed = time.time() - started
    print(f"\n{C.BOLD}{C.CYAN}{'═'*60}")
    print(f"  DONE in {elapsed:.1f}s")
    print(f"  ✓ Success: {successes}")
    print(f"  ✗ Failed:  {failures}")
    print(f"  → {OUTPUT_SUCCESS}")
    print(f"  → {OUTPUT_FAILED}")
    print(f"{'═'*60}{C.RESET}")

if __name__ == "__main__":
    main()