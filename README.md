# AI Multi-Website Research

This Streamlit app compares information from four or five public websites.
It fetches bounded, same-domain HTML content, removes non-readable elements,
and asks OpenAI to produce a source-cited comparison.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Create `.streamlit/secrets.toml` locally (do not commit it):

```toml
APP_PASSWORD = "choose-a-password"
OPENAI_API_KEY = "your-openai-key"
```

The password protects the app. The API key may instead be entered in the
sidebar. `OPENAI_MODEL` can optionally be set as an environment variable.

## Use the app

1. Unlock the app with the configured password.
2. Enter four or five unique public HTTP(S) URLs.
3. Enter the task and comparison criteria.
4. Choose the maximum number of same-domain pages to read per website.
5. Click **Analyze websites** and optionally download the Markdown result.

Each website is limited to ten pages and the combined extracted content is
limited to 48,000 characters. Private, loopback, link-local, reserved, and
credential-bearing URLs are rejected. Non-HTML responses are skipped.

## Tests

```bash
python -m unittest discover -s tests -v
```

The GitHub Actions workflow runs the same command on pushes and pull requests.

## Streamlit Community Cloud

Deploy the repository with `app.py` as the entry point. In the app settings,
add these secrets:

```toml
APP_PASSWORD = "choose-a-password"
OPENAI_API_KEY = "your-openai-key"
```

Never commit `.streamlit/secrets.toml` or API keys. The included
`.streamlit/config.toml` disables anonymous usage-stat collection and enables
headless server operation.

## Limitations

The crawler cannot execute JavaScript, bypass logins, interpret PDFs, or
guarantee that every important page is linked from the starting page. Website
content is supplied to an AI model, so users should review the cited sources
and avoid submitting private or sensitive URLs.
