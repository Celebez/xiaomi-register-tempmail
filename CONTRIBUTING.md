# Contributing

Thanks for considering contributing! Here's how to get started.

## Development Setup

1. **Fork & clone** the repo:

```bash
git clone https://github.com/YOUR_USERNAME/xiaomi-register-tempmail.git
cd xiaomi-register-tempmail
```

2. **Create a venv** (Python 3.10+ required):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. **Install Node.js dependency**:

```bash
cd scripts && npm install crypto-js && cd ..
```

4. **Test your setup**:

```bash
python batch_tempmail.py --dry-run --count 1
```

You should see mail.tm inbox creation + simulated 8-step flow.

## Submitting Changes

1. **Create a branch** from `main`:

```bash
git checkout -b feat/your-feature-name
```

2. **Make changes** and verify:
   - Run `python -m py_compile batch_tempmail.py` (syntax check)
   - Run `python batch_tempmail.py --dry-run --count 1` (functional test)
   - Run `python batch_tempmail.py --help` (CLI surface)

3. **Commit** with a descriptive message:

```bash
git commit -m "Add support for 1secmail provider"
```

4. **Push** and open a Pull Request:

```bash
git push origin feat/your-feature-name
gh pr create --title "Add 1secmail support" --body "..."
```

CI will automatically run Python syntax check, JSON validation, and Node.js bridge test.

## Reporting Issues

Use the issue templates:
- 🐛 [Bug report](.github/ISSUE_TEMPLATE/bug_report.md)
- 💡 [Feature request](.github/ISSUE_TEMPLATE/feature_request.md)
- ❓ [Question](.github/ISSUE_TEMPLATE/question.md)

## Code Style

- Python: PEP 8, use type hints where helpful
- Functions: docstring for every public function
- Error handling: explicit exception types, don't bare `except:`
- Output: use the `info/ok/warn/err/step` helpers for consistency
- Comments: explain *why*, not *what*

## Areas for Contribution

Looking for ideas? Check these:

- [ ] Add 1secmail provider as alternative to mail.tm
- [ ] Add guerrillamail provider (more domain choices)
- [ ] Hybrid mode: Gmail IMAP fallback when temp mail fails
- [ ] Dockerfile for one-command setup
- [ ] Tests with pytest + mocked HTTP responses
- [ ] Proxy rotation support
- [ ] Multi-language README (English version)
- [ ] Captcha solver plugins (CapSolver, Anti-Captcha in addition to 2Captcha)
- [ ] Web UI for non-technical users

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).