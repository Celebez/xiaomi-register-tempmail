# Xiaomi Account Registration — Temp Mail (mail.tm) Edition

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Modified from [`guajiimi/xiaomi-register`](https://github.com/guajiimi/xiaomi-register) to use **mail.tm** as disposable email provider instead of Gmail IMAP. Registers N Xiaomi accounts in batch — each account gets its own mail.tm inbox, receives the verification code there, and gets created fully automatically via reverse-engineered Xiaomi API flow.

## ⚠️ Important Disclaimers

1. **mail.tm has only 1 active domain currently: `@web-library.net`** — Xiaomi may blacklist this domain since it's a known temp mail service. Expect lower success rate than Gmail-based version.
2. **mail.tm rate-limits aggressively** — script handles 429 with backoff, but you may need `--sleep 30+` for >10 accounts.
3. **2Captcha costs money** — each reCAPTCHA Enterprise solve is ~$0.002. Budget ~$0.05 per account with retries.
4. **Mass account creation likely violates Xiaomi ToS** — use at your own risk. This tool is for educational/research purposes only.

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
# + mailtm if not included
pip install mailtm requests

# Node.js deps for EUI encryption
cd scripts && npm install crypto-js && cd ..
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env, add your 2Captcha API key from https://2captcha.com
```

### 3. Run

```bash
# Register 10 accounts (default)
python batch_tempmail.py

# Register 25 accounts
python batch_tempmail.py --count 25

# Resume after interruption
python batch_tempmail.py --resume

# Custom delay between accounts
python batch_tempmail.py --sleep 30
```

## 📦 Output Files

| File | Contents |
|------|----------|
| `accounts.jsonl` | One JSON per line for each SUCCESS: `{email, password, cookies, created_at}` |
| `failed.jsonl` | One JSON per line for each FAILURE: `{email, password, stage, error}` |

### Example success line
```json
{"status": "success", "email": "mxa8k3j9f2x@web-library.net", "password": "xK9$mP2qL!nZ", "cookies": {"passToken": "abc...", "serviceToken": "def..."}, "created_at": "2026-06-20T05:30:00Z"}
```

## 🔄 8-Step Registration Flow

1. **Warm-up** — GET register page → collect cookies
2. **Captcha data** — POST encrypted fingerprint → get `e_token`
3. **Solve reCAPTCHA** — via 2Captcha → get `gRecaptchaResponse`
4. **Verify captcha** — exchange for `vToken`
5. **Encrypt credentials** — AES+RSA via Node.js `encrypt.cjs`
6. **Send reg ticket** — POST to `sendEmailRegTicket` with `vToken` cookie
7. **Poll mail.tm inbox** — wait for 6-digit code from `noreply@notice.xiaomi.com`
8. **Verify code** — POST to `verifyEmailRegTicket` → account created

For deep technical details, see [`docs/FLOW.md`](docs/FLOW.md).

## 🆚 Differences From Original `guajiimi/xiaomi-register`

| Aspect | Original | This Script |
|--------|----------|-------------|
| Email inbox | Gmail IMAP | mail.tm HTTP API |
| Path hardcoded | `/root/xiaomi-register/...` | Relative `SCRIPT_DIR/...` |
| Single account | Yes | Batch with loop |
| Resume support | No | `--resume` flag |
| Rate limit handling | None | 429 retry + backoff |
| Cross-platform | Linux only | Linux/Mac/Windows |

## 🔧 Troubleshooting

**`encrypt.cjs failed: Cannot find module 'crypto-js'`**
```bash
cd scripts && npm install crypto-js && cd ..
```

**`mail.tm 429 Too Many Requests`**
→ Increase `--sleep` to 30-60 seconds. mail.tm limits anonymous users to ~3-5 accounts/minute.

**`captcha/v2/data failed: 400`**
→ `docs/payload_template.json` is stale. Regenerate via Playwright capture (see original repo for `dump_payload.mjs`).

**`verifyEmailRegTicket failed`**
→ Most common cause: Xiaomi blacklisted `@web-library.net` domain. Switch to Gmail IMAP (use original `register.py`) or try a different temp mail provider like 1secmail.

## 📄 License

MIT — same as the original [`guajiimi/xiaomi-register`](https://github.com/guajiimi/xiaomi-register).

## 🙏 Credits

- Original script and reverse-engineering work: [`guajiimi`](https://github.com/guajiimi)
- mail.tm API: [mail.tm](https://docs.mail.tm)
- 2Captcha service: [2captcha.com](https://2captcha.com)