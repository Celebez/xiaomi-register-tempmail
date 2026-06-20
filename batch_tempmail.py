#!/usr/bin/env python3
"""
Xiaomi Account Batch Registration — Temp Mail (mail.tm) Edition
===============================================================

Registers N Xiaomi accounts in batch using mail.tm disposable email — no Gmail
or personal email setup required. Each account gets its own private mail.tm
inbox, receives the 6-digit verification code from Xiaomi there, and gets
created fully automatically via the reverse-engineered 8-step Xiaomi API flow.

Flow (per account):
  1. Warm-up: GET register page
  2. POST captcha/v2/data with encrypted browser fingerprint → e_token
  3. Solve reCAPTCHA Enterprise via 2Captcha → gRecaptchaResponse
  4. POST captcha/v2/recaptcha/verify → vToken (cookie)
  5. Encrypt email+password (AES+RSA via Node.js encrypt.cjs)
  6. POST sendEmailRegTicket with vToken cookie → code emailed
  7. Poll mail.tm inbox for 6-digit code from noreply@notice.xiaomi.com
  8. POST verifyEmailRegTicket → account created, cookies returned

Usage:
    python batch_tempmail.py                  # register 10 accounts (default)
    python batch_tempmail.py --count 25       # register 25 accounts
    python batch_tempmail.py --resume         # skip already-registered emails
    python batch_tempmail.py --dry-run        # simulate without 2Captcha

Prerequisites:
    - Python 3.10+
    - Node.js 18+ (for scripts/encrypt.cjs)
    - pip install -r requirements.txt
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
from abc import ABC, abstractmethod
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

# Captcha provider endpoints — all use the same RecaptchaV2EnterpriseTaskProxyless task format.
# Override at runtime via --captcha-provider flag or CAPTCHA_PROVIDER env var.
CAPTCHA_PROVIDERS = {
    "2captcha": {
        "name": "2Captcha",
        "create": "https://api.2captcha.com/createTask",
        "result": "https://api.2captcha.com/getTaskResult",
        "signup": "https://2captcha.com",
        "free_credit": "None",
        "cost_per_solve": "$0.003",
    },
    "capsolver": {
        "name": "CapSolver",
        "create": "https://api.capsolver.com/createTask",
        "result": "https://api.capsolver.com/getTaskResult",
        "signup": "https://dashboard.capsolver.com/signup",
        "free_credit": "$1 (no payment method)",
        "cost_per_solve": "$0.0015",
    },
    "anticaptcha": {
        "name": "Anti-Captcha",
        "create": "https://api.anti-captcha.com/createTask",
        "result": "https://api.anti-captcha.com/getTaskResult",
        "signup": "https://anti-captcha.com",
        "free_credit": "$5 (phone verify)",
        "cost_per_solve": "$0.002",
    },
    "capmonster": {
        "name": "CapMonster Cloud",
        "create": "https://api.capmonster.cloud/createTask",
        "result": "https://api.capmonster.cloud/getTaskResult",
        "signup": "https://capmonster.cloud",
        "free_credit": "Refundable $5 trial",
        "cost_per_solve": "$0.0015",
    },
}

# Default endpoints — may be overridden at runtime by configure_captcha_provider()
TWOCAPTCHA_CREATE = CAPTCHA_PROVIDERS["2captcha"]["create"]
TWOCAPTCHA_RESULT = CAPTCHA_PROVIDERS["2captcha"]["result"]


def configure_captcha_provider(name: str) -> dict:
    """Switch active captcha endpoints. Returns provider info dict."""
    key = name.lower().strip()
    if key not in CAPTCHA_PROVIDERS:
        raise ValueError(
            f"Unknown CAPTCHA provider: '{name}'. "
            f"Available: {', '.join(CAPTCHA_PROVIDERS.keys())}"
        )
    info = CAPTCHA_PROVIDERS[key]
    globals()["TWOCAPTCHA_CREATE"] = info["create"]
    globals()["TWOCAPTCHA_RESULT"] = info["result"]
    return info

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

# ─── Temp Mail Provider Interface + Implementations ───────────────────────────
class TempMailProvider(ABC):
    """Abstract interface for disposable email providers.

    Each provider returns a fresh inbox where Xiaomi's verification code
    can be received and polled.
    """
    address: str  # The email address assigned to this inbox

    @abstractmethod
    def create(self) -> str:
        """Initialize a new inbox. Returns the email address."""

    @abstractmethod
    def get_messages(self) -> list:
        """Return list of messages in the inbox (lightweight metadata)."""

    @abstractmethod
    def get_message_content(self, msg_id: str) -> str:
        """Return full body text/HTML of a specific message."""

    @abstractmethod
    def delete(self):
        """Best-effort cleanup. May be a no-op for some providers."""

    def wait_for_verification_code(self, sender_hint: str = "xiaomi", timeout: int = 180) -> str:
        """Poll inbox until a 6-digit code from the sender appears. Returns the code."""
        deadline = time.time() + timeout
        seen_ids = set()
        info(f"Polling {self.address} for code (timeout {timeout}s)...")

        while time.time() < deadline:
            try:
                msgs = self.get_messages()
                for m in msgs:
                    # Extract message ID (provider-specific field name)
                    msg_id = str(m.get("id") or m.get("_id") or m.get("mail_id") or "")
                    if not msg_id or msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)
                    # Extract sender — handle different formats
                    frm = ""
                    if isinstance(m.get("from"), dict):
                        frm = m["from"].get("address", "")
                    elif isinstance(m.get("from"), str):
                        frm = m["from"]
                    elif m.get("mail_from"):
                        frm = m["mail_from"]
                    subj = m.get("subject", "") or m.get("mail_subject", "")
                    if sender_hint.lower() in frm.lower() or sender_hint.lower() in subj.lower() or "notice" in frm.lower():
                        body = self.get_message_content(msg_id)
                        body = body.replace("=\r\n", "").replace("=\n", "")
                        match = re.search(r"verification code is[:\s]*(\d{6})", body, re.IGNORECASE)
                        if match:
                            code = match.group(1)
                            ok(f"Code received: {code}")
                            return code
            except Exception as e:
                warn(f"Poll error: {e}")
            time.sleep(5)

        raise TimeoutError(f"No code received within {timeout}s for {self.address}")


class MailTmProvider(TempMailProvider):
    """mail.tm — private inbox, 1 active domain (web-library.net).

    Pros: Private inbox, real account creation, clean API
    Cons: Only 1 domain, aggressive rate limits (429), likely blacklisted by Xiaomi
    """
    BASE = "https://api.mail.tm"

    def __init__(self, password: str):
        self.password = password
        self.account_id = None
        self.token = None
        # mail.tm's anti-bot returns XML when curl_cffi's Chrome fingerprint is used.
        # Plain session (no impersonate) works fine.
        self.session = cffi_requests.Session()

    def _request(self, method: str, url: str, max_retries: int = 3, **kwargs):
        last_err = None
        for attempt in range(max_retries):
            try:
                method_fn = getattr(self.session, method.lower())
                r = method_fn(url, **kwargs)
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 10)) + random.randint(2, 5)
                    warn(f"mail.tm rate limited (429), waiting {wait}s...")
                    time.sleep(wait)
                    continue
                return r
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"mail.tm {method} {url} failed: {last_err}")

    def _get_domain(self) -> str:
        r = self._request("GET", f"{self.BASE}/domains", timeout=15)
        data = r.json()
        if isinstance(data, dict):
            domains = data.get("hydra:member", [])
        else:
            domains = data
        if not domains:
            raise RuntimeError("No mail.tm domains available")
        for d in domains:
            if isinstance(d, dict) and d.get("isActive"):
                return d["domain"]
        first = domains[0]
        if isinstance(first, dict):
            return first["domain"]
        raise RuntimeError(f"Unexpected domain format: {first}")

    def create(self) -> str:
        domain = self._get_domain()
        local = "mx" + ''.join(random.choices(string.digits + string.ascii_lowercase, k=10))
        self.address = f"{local}@{domain}"
        r = self._request("POST", f"{self.BASE}/accounts", timeout=15,
                          json={"address": self.address, "password": self.password})
        if r.status_code >= 400:
            raise RuntimeError(f"mail.tm account create failed: {r.status_code} {r.text[:200]}")
        self.account_id = r.json()["id"]
        self._refresh_token()
        return self.address

    def _refresh_token(self):
        r = self._request("POST", f"{self.BASE}/token", timeout=15,
                          json={"address": self.address, "password": self.password})
        if r.status_code >= 400:
            raise RuntimeError(f"mail.tm token failed: {r.status_code} {r.text[:200]}")
        self.token = r.json()["token"]

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def get_messages(self) -> list:
        r = self._request("GET", f"{self.BASE}/messages", timeout=15, headers=self._headers())
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, dict):
            return data.get("hydra:member", [])
        return data if isinstance(data, list) else []

    def get_message_content(self, msg_id: str) -> str:
        r = self._request("GET", f"{self.BASE}/messages/{msg_id}", timeout=15,
                          headers=self._headers())
        if r.status_code != 200:
            return ""
        data = r.json()
        return " ".join(filter(None, [data.get("intro", ""), data.get("text", ""), data.get("html", "")]))

    def delete(self):
        try:
            if self.account_id:
                self._request("DELETE", f"{self.BASE}/accounts/{self.account_id}",
                              timeout=10, headers=self._headers())
        except Exception:
            pass


class GuerrillaMailProvider(TempMailProvider):
    """Guerrilla Mail — rotates among 11+ domains, no signup needed.

    Pros: Many domains (less likely to be all blacklisted), no auth, sid_token auth
    Cons: Public-ish (anyone with sid_token can read), 60-min email lifetime
    """
    BASE = "https://api.guerrillamail.com/ajax.php"

    def __init__(self):
        self.sid_token = None
        self.alias = None
        # Need Chrome impersonation to bypass their anti-bot
        self.session = cffi_requests.Session(impersonate="chrome124")

    def _get(self, action: str, **extra):
        params = {"f": action, "lang": "en"}
        params.update(extra)
        if self.sid_token:
            params["sid_token"] = self.sid_token
        r = self.session.get(self.BASE, params=params, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"Guerrilla {action} failed: {r.status_code} {r.text[:200]}")
        return r.json()

    def create(self) -> str:
        data = self._get("get_email_address")
        self.address = data["email_addr"]
        self.sid_token = data["sid_token"]
        self.alias = data.get("alias")
        return self.address

    def get_messages(self) -> list:
        data = self._get("get_email_list", offset=0)
        return data.get("list", [])

    def get_message_content(self, msg_id: str) -> str:
        # msg_id is the mail_id from get_email_list
        data = self._get("fetch_email", email_id=msg_id)
        # Combine all body fields
        return " ".join(filter(None, [
            data.get("mail_subject", ""),
            data.get("mail_body", ""),
            data.get("mail_excerpt", ""),
            data.get("mail_html", ""),  # might not exist
        ]))

    def delete(self):
        # Guerrilla emails auto-expire in 60 min — no explicit delete needed
        pass


class HarakiriProvider(TempMailProvider):
    """Harakirimail — pick any name, public inbox, NO signup, NO auth.

    Pros: Zero setup, no rate limits, no signup
    Cons: Public inbox (anyone knowing the name can read), emails expire in 1 hour
    Note: The 'inbox name' acts as the email local-part. Use a unique random name.
    """
    BASE = "https://harakirimail.com/api/v1"

    def __init__(self):
        self.session = cffi_requests.Session()
        self.name = None  # The unique inbox name (local-part)

    def create(self) -> str:
        # Generate a unique random name with very low collision probability
        self.name = "mx" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=14))
        self.address = f"{self.name}@harakirimail.com"
        # No signup needed — just verify the inbox exists
        r = self.session.get(f"{self.BASE}/inbox/{self.name}", timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"Harakiri inbox check failed: {r.status_code}")
        return self.address

    def get_messages(self) -> list:
        r = self.session.get(f"{self.BASE}/inbox/{self.name}", timeout=15)
        if r.status_code != 200:
            return []
        return r.json().get("emails", [])

    def get_message_content(self, msg_id: str) -> str:
        # Fetch specific email by ID
        r = self.session.get(f"{self.BASE}/email/{msg_id}", timeout=15)
        if r.status_code != 200:
            return ""
        data = r.json()
        # Combine available fields
        body = data.get("body", "") or data.get("html", "") or data.get("text", "")
        # If empty, try the whole object as JSON string
        if not body:
            body = json.dumps(data)
        return " ".join(filter(None, [
            data.get("subject", ""),
            body,
            data.get("from", ""),
        ]))

    def delete(self):
        # Harakiri emails auto-expire in 1 hour
        pass


# Provider registry — add new providers here
TEMPMAIL_PROVIDERS = {
    "mailtm": MailTmProvider,
    "guerrillamail": GuerrillaMailProvider,
    "harakiri": HarakiriProvider,
}


def get_temp_mail_provider(name: str = None, password: str = "MxBatchPass2026!") -> TempMailProvider:
    """Factory: instantiate a temp mail provider by name.

    Default provider is read from TEMPMAIL_PROVIDER env var, or 'mailtm' if unset.
    Valid values: mailtm, guerrillamail, harakiri
    """
    name = (name or os.getenv("TEMPMAIL_PROVIDER", "mailtm")).lower().strip()
    if name not in TEMPMAIL_PROVIDERS:
        available = ", ".join(sorted(TEMPMAIL_PROVIDERS.keys()))
        raise ValueError(f"Unknown TEMPMAIL_PROVIDER: '{name}'. Available: {available}")
    cls = TEMPMAIL_PROVIDERS[name]
    # Only MailTmProvider needs password
    if cls == MailTmProvider:
        return cls(password=os.getenv("MAILTM_PASSWORD_BASE", password))
    return cls()


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

def step2_captcha_data(session, tm: TempMailProvider):
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

def register_one(idx: int, total: int, api_key: str, mailtm_password: str,
                 provider_name: str = None, dry_run: bool = False) -> dict:
    """Register one account. Returns dict with status, email, password, error.

    If dry_run=True, sets up mail.tm inbox + generates password + simulates the
    8-step flow with fake but realistic-looking output (no actual Xiaomi calls,
    no 2Captcha charges). Useful for testing setup and recording demos.
    """
    print(f"\n{C.BOLD}{C.CYAN}{'═'*60}")
    print(f"  Account {idx+1}/{total}{' [DRY RUN]' if dry_run else ''}")
    print(f"{'═'*60}{C.RESET}")

    # Setup temp mail
    tm = get_temp_mail_provider(name=provider_name, password=mailtm_password)
    try:
        address = tm.create()
        info(f"Inbox created: {address}")
    except Exception as e:
        err(f"temp mail setup failed: {e}")
        return {"status": "failed", "stage": "tempmail_setup", "error": str(e)}

    password = generate_xiaomi_password()
    session = make_session()
    vtoken: str = ""

    if dry_run:
        # Simulate the 8-step flow without making actual Xiaomi/2Captcha calls
        time.sleep(0.4)
        info(f"Generated password: {password}")
        time.sleep(0.2)
        step("[DRY] Step 1/8 — GET register page (warm-up)")
        time.sleep(0.3)
        ok("Status: 200, cookies: {'locale': 'en_US'}")
        time.sleep(0.2)
        step("[DRY] Step 2/8 — POST captcha/v2/data (encrypted fingerprint)")
        time.sleep(0.3)
        fake_e_token = "e_" + ''.join(random.choices(string.ascii_letters + string.digits, k=64))
        ok(f"e_token: {fake_e_token[:32]}...")
        time.sleep(0.2)
        step("[DRY] Step 3/8 — Solving reCAPTCHA Enterprise via 2Captcha...")
        time.sleep(0.3)
        fake_task_id = str(uuid.uuid4())
        info(f"Task ID: {fake_task_id}")
        for attempt in range(3):
            time.sleep(0.3)
            info(f"Poll {attempt+1}: status=processing...")
        time.sleep(0.3)
        ok("Captcha solved")
        time.sleep(0.2)
        step("[DRY] Step 4/8 — POST captcha/v2/recaptcha/verify")
        time.sleep(0.3)
        vtoken = "v_" + ''.join(random.choices(string.ascii_letters + string.digits, k=128))
        ok(f"vToken: {vtoken[:50]}...")
        time.sleep(0.2)
        step("[DRY] Step 5/8 — Encrypting email+password (EUI)")
        time.sleep(0.3)
        try:
            eui, _ = build_eui({"email": address, "password": password})
            ok(f"EUI: {eui[:50]}...")
        except Exception as e:
            warn(f"EUI skipped (Node.js setup issue): {e}")
        time.sleep(0.2)
        step("[DRY] Step 6/8 — POST sendEmailRegTicket")
        time.sleep(0.3)
        ok(f"Code sent to {address}")
        info("Mengunggu kode verifikasi masuk...")
        time.sleep(0.2)
        step("[DRY] Step 7/8 — Polling mail.tm inbox...")
        time.sleep(0.6)
        fake_code = ''.join(random.choices(string.digits, k=6))
        ok(f"Code received: {fake_code}")
        time.sleep(0.2)
        step("[DRY] Step 8/8 — POST verifyEmailRegTicket (creating account)")
        time.sleep(0.4)
        ok(f"Account created: {address}")
        time.sleep(0.2)
        print(f"\n{C.BOLD}{C.GREEN}{'─'*60}")
        print(f"  ✓ [DRY RUN] Account ready: {address} / {password}")
        print(f"{'─'*60}{C.RESET}")
        return {
            "status": "success",
            "email": address,
            "password": password,
            "cookies": {
                "passToken": "[DRY_RUN_FAKE_TOKEN]",
                "serviceToken": "[DRY_RUN_FAKE_TOKEN]",
                "cUserId": str(random.randint(100000000, 999999999)),
                "userId": str(random.randint(100000000, 999999999)),
            },
            "dry_run": True,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

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
        code = tm.wait_for_verification_code(timeout=180)

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
    parser.add_argument("--dry-run", action="store_true",
                       help="Setup temp mail inbox + simulate the 8-step flow without "
                            "actually calling Xiaomi or 2Captcha. Free, no API key needed.")
    parser.add_argument("--provider", "-p", default=None,
                       help="Temp mail provider: mailtm, guerrillamail, harakiri "
                            "(default: TEMPMAIL_PROVIDER env var or 'mailtm')")
    parser.add_argument("--captcha-provider", "-c", default=None,
                       help="Captcha solving service: 2captcha, capsolver, anticaptcha, capmonster "
                            "(default: CAPTCHA_PROVIDER env var or '2captcha'). "
                            "Use 'capsolver' for $1 free trial.")
    args = parser.parse_args()

    api_key = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
    mailtm_password = os.getenv("MAILTM_PASSWORD_BASE", "MxBatchPass2026!")
    provider_name = args.provider or os.getenv("TEMPMAIL_PROVIDER", "mailtm")
    captcha_name = args.captcha_provider or os.getenv("CAPTCHA_PROVIDER", "2captcha")

    if not api_key and not args.dry_run:
        err("TWOCAPTCHA_API_KEY not set in .env (or use --dry-run)")
        sys.exit(1)

    # Validate provider name early
    try:
        get_temp_mail_provider(name=provider_name, password=mailtm_password)
    except ValueError as e:
        err(str(e))
        sys.exit(1)

    # Switch captcha provider endpoints
    try:
        captcha_info = configure_captcha_provider(captcha_name)
    except ValueError as e:
        err(str(e))
        sys.exit(1)

    print(f"{C.BOLD}{C.MAGENTA}")
    print("┌──────────────────────────────────────────────┐")
    print("│  Xiaomi Batch Register — Temp Mail Edition   │")
    print(f"│  Mail: {provider_name:<10}  Captcha: {captcha_info['name']:<10} │")
    print(f"│  Count: {args.count:<3}   Cost/solve: {captcha_info['cost_per_solve']:<6}        │")
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

        result = register_one(i, args.count, api_key, mailtm_password,
                              provider_name=provider_name, dry_run=args.dry_run)

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