## 🎉 First stable release

Initial public release of **xiaomi-register-tempmail** — a batch Xiaomi account registration tool using mail.tm disposable email.

### What's included

- `batch_tempmail.py` — main script with full 8-step Xiaomi API flow
- `docs/demo.gif` — animated demo of `--dry-run` mode
- `docs/FLOW.md` — reverse-engineering notes for the 8-step flow
- `docs/payload_template.json` — browser fingerprint template
- `scripts/encrypt.cjs` — Node.js bridge for AES+RSA EUI encryption
- 12-step Linux install instructions (Ubuntu / Fedora / Arch)
- GitHub Actions CI: Python syntax check + JSON validation + Node.js bridge test

### Features

- ✅ `--count N` for batch size
- ✅ `--resume` to skip already-registered emails
- ✅ `--start-from N` to resume from specific index
- ✅ `--sleep N` for delay between accounts
- ✅ `--dry-run` for testing without 2Captcha charges
- ✅ 429 rate-limit handling with exponential backoff for mail.tm
- ✅ Auto-retry for captcha solve (up to 4 attempts per account)
- ✅ Per-account JSONL output (`accounts.jsonl` / `failed.jsonl`)

### Quick start

```bash
git clone https://github.com/Celebez/xiaomi-register-tempmail.git
cd xiaomi-register-tempmail
pip install -r requirements.txt
cd scripts && npm install crypto-js && cd ..
cp .env.example .env  # add TWOCAPTCHA_API_KEY
python batch_tempmail.py --count 10
```

### Cost estimate

- mail.tm: **free**
- 2Captcha: ~$0.003 per solve (~$0.05 for 10 accounts with retries)

### ⚠️ Disclaimer

Mass account creation likely violates Xiaomi ToS. Use at your own risk. Intended for educational and research purposes only.

---

**Full Changelog**: https://github.com/Celebez/xiaomi-register-tempmail/blob/main/CHANGELOG.md