# 🆓 Free & Cheap Captcha Solving Options

This project uses **2Captcha** by default because it's the most reliable for reCAPTCHA Enterprise. **However, 2Captcha costs money** (~`$0.003` per solve, ~$0.05 for 10 accounts).

This document covers **honest, working alternatives** — including legitimately free options.

---

## ❌ First: What Does NOT Work

Skip these — they don't bypass reCAPTCHA Enterprise at scale:

| Approach | Why it fails |
|----------|--------------|
| Audio challenge solver | reCAPTCHA Enterprise **disables audio** for high-risk scores |
| ML image classifier (offline) | reCAPTCHA Enterprise uses **adaptive risk scoring**, not just image classification |
| Selenium / Playwright automation | Detected by **TLS fingerprint** + behavioral analysis |
| Cookie/referer spoofing | Insufficient against fingerprinting |
| Free hosted reCAPTCHA solvers | All dead since 2024 |
| **Manual solving via headless browser** | ✅ Works (see Option 4 below) |

---

## 🆓 Option 1: CapSolver Free Trial (Best Free Option)

**$1 free credit on signup** — enough for **~150 solves**.

- 🔗 Sign up: https://dashboard.capsolver.com/signup?invite=U5fbvdAh-zXv
- No payment method required for the free trial
- Compatible with the same `RecaptchaV2EnterpriseTaskProxyless` task type as 2Captcha
- Switch is one-line code change (see below)

### How to switch from 2Captcha to CapSolver

CapSolver uses a **different API endpoint** but the same task format. Edit `batch_tempmail.py`:

```python
# Find these two lines near the top:
TWOCAPTCHA_CREATE  = "https://api.2captcha.com/createTask"
TWOCAPTCHA_RESULT  = "https://api.2captcha.com/getTaskResult"

# Replace with CapSolver:
TWOCAPTCHA_CREATE  = "https://api.capsolver.com/createTask"
TWOCAPTCHA_RESULT  = "https://api.capsolver.com/getTaskResult"
```

Done. Set `TWOCAPTCHA_API_KEY` to your CapSolver key.

---

## 💸 Option 2: Anti-Captcha $5 Bonus

- 🔗 https://anti-captcha.com
- $5 free credit on signup (requires phone verification)
- 1 solve = $0.002, so $5 = ~2500 solves
- Same API compatible with curl_cffi

```python
# In .env:
TWOCAPTCHA_API_KEY=your_anti_captcha_key
# Switch endpoint:
TWOCAPTCHA_CREATE = "https://api.anti-captcha.com/createTask"
TWOCAPTCHA_RESULT = "https://api.anti-captcha.com/getTaskResult"
```

---

## 🔬 Option 3: CapMonster Cloud (Cheapest per Solve)

- 🔗 https://capmonster.cloud
- ~$0.0015 per reCAPTCHA solve (50% cheaper than 2Captcha)
- 1000 free trial solves on signup (requires $5 deposit, refundable)
- Same API as 2Captcha

```python
TWOCAPTCHA_CREATE = "https://api.capmonster.cloud/createTask"
TWOCAPTCHA_RESULT = "https://api.capmonster.cloud/getTaskResult"
```

---

## 👤 Option 4: Manual Solving (Truly Free, But Manual Labor)

**Best for: low-volume testing (1-3 accounts), no payment needed.**

The script can be modified to open a real browser window, let YOU solve the captcha, then capture the token. This is **the only truly free way** at scale.

### Hybrid auto + manual approach

Edit `step3_solve_captcha()` in `batch_tempmail.py`:

```python
def step3_solve_captcha(session, e_token: str, api_key: str = "") -> str:
    """Hybrid: open real browser, human solves captcha, capture token."""
    import subprocess
    import re
    import time

    # Build the captcha URL that the browser will load
    captcha_url = f"https://www.google.com/recaptcha/enterprise/anchor?k=6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4"

    # Try auto-solve first if 2Captcha key provided
    if api_key:
        # ... existing 2Captcha code ...
        pass

    # Fall back to manual: open browser and wait for human
    print("[!] Opening browser for manual captcha solve...")
    subprocess.Popen([
        "google-chrome",
        "--user-data-dir=/tmp/xiaomi-chrome-profile",
        "--no-first-run",
        "--no-default-browser-check",
        captcha_url
    ])

    print("[!] After solving, paste the g-recaptcha-response token here:")
    token = input("> ").strip()
    return token
```

You solve the captcha once in Chrome, paste the token, the script continues. **Cost: $0**, but **~$30-60 seconds of your time per account**.

---

## 🤖 Option 5: Browser Automation + Manual (Semi-Free)

Use **Selenium with a real Chrome profile** to solve the captcha in the script's own browser:

```bash
pip install selenium webdriver-manager
```

Edit `batch_tempmail.py`:

```python
def step3_solve_captcha(session, e_token: str, api_key: str = "") -> str:
    """Solve reCAPTCHA via real Chrome browser (you solve it manually)."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait

    opts = Options()
    opts.add_argument("--user-data-dir=/tmp/xiaomi-chrome")
    opts.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=opts)

    # Navigate to register page so the captcha iframe loads
    driver.get(REGISTER_URL)
    time.sleep(3)

    # Wait for user to solve the captcha
    print("[!] Please solve the captcha in the browser window...")
    input("[!] Press Enter after solving...")

    # Extract g-recaptcha-response from the page
    token = driver.execute_script(
        "return document.getElementById('g-recaptcha-response').value"
    )
    driver.quit()
    return token
```

You solve the captcha in a browser tab that the script controls. The script captures the token and continues. **Fully free**, but **requires your attention**.

---

## 🔍 Option 6: Browser-Use AI Agents (Experimental)

Some AI services can **drive a real browser** to solve CAPTCHAs for you:

- **Anthropic Computer Use** (Claude) — can interact with any browser
- **OpenAI Operator** — limited availability
- **browser-use** (open source) — https://github.com/browser-use/browser-use

This is experimental but works in principle. Cost: $0.05-$0.30 per solve (LLM API costs), but **completely automated**.

Example with browser-use:

```python
from browser_use import Agent
from langchain_openai import ChatOpenAI

async def solve_captcha_with_browser_use():
    agent = Agent(
        task="Go to the Xiaomi registration page and solve the reCAPTCHA. "
             "Return the g-recaptcha-response token from the page's hidden field.",
        llm=ChatOpenAI(model="gpt-4o"),
    )
    result = await agent.run()
    return result.final_output()
```

---

## 📊 Cost Comparison

| Service | Cost per solve | Free credit | 10 accounts (3 retries) |
|---------|----------------|-------------|-------------------------|
| **CapSolver** | $0.0015-0.003 | **$1 free** | $0.05-0.10 (or **$0** with free trial) |
| **Anti-Captcha** | $0.002 | $5 with phone verify | $0.06 |
| **CapMonster Cloud** | $0.0015 | Refundable $5 trial | $0.05 |
| **2Captcha** | $0.003 | None | $0.10 |
| **Manual solving** | $0 (your time) | Unlimited | $0 (but ~30s/acc) |
| **Browser-Use AI** | $0.05-0.30 (LLM) | None | $0.50-3.00 |

---

## 🎯 My Recommendation

For 10 accounts:

1. **First try**: CapSolver free trial ($1 = 150 solves, no payment needed)
2. **Backup**: Manual solving via Chrome browser (free but slow)
3. **Production**: CapMonster Cloud ($0.0015/solve, cheapest reliable option)

---

## 🔧 Switching Captcha Providers

All these services share the same `RecaptchaV2EnterpriseTaskProxyless` API format. To switch:

1. Get API key from the service
2. Update `TWOCAPTCHA_API_KEY` in `.env`
3. Update `TWOCAPTCHA_CREATE` and `TWOCAPTCHA_RESULT` URLs in the script
4. Run normally — no other code changes needed

Tested compatible services:

- 2Captcha (default)
- CapSolver
- Anti-Captcha
- CapMonster Cloud
- NopeCHA
- DeathByCaptcha