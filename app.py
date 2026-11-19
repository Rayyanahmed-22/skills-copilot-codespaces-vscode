import hashlib
import ipaddress
import os
import socket
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import APIError, OpenAI


MAX_PAGE_CHARS = 12_000
MAX_TOTAL_CHARS = 48_000
MAX_PROMPT_CHARS = 120_000
DEFAULT_MAX_PAGES = 3
MAX_ALLOWED_PAGES = 10
REQUEST_TIMEOUT = 15
USER_AGENT = "MultiWebsiteResearch/2.0"


def _public_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 80, 443}
    ):
        raise ValueError("Only public HTTP(S) URLs without credentials are supported.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise ValueError("The website hostname could not be resolved.") from None
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Only public HTTP(S) URLs are supported.")
    return url


def extract_page(html: str, base_url: str) -> tuple[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "template"]):
        element.decompose()
    text = " ".join(soup.stripped_strings)
    links = []
    for anchor in soup.find_all("a", href=True):
        link, _ = urldefrag(urljoin(base_url, anchor["href"]))
        if urlparse(link).scheme in {"http", "https"}:
            links.append(link)
    return text[:MAX_PAGE_CHARS], links


def _fetch_document(url: str) -> tuple[str, list[str]]:
    safe_url = _public_url(url)
    for _ in range(4):
        response = requests.get(
            safe_url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise ValueError("The website returned an invalid redirect.")
            safe_url = _public_url(urljoin(safe_url, location))
            continue
        break
    else:
        raise ValueError("The website used too many redirects.")
    response.raise_for_status()
    final_url = _public_url(response.url)
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "text/html" not in content_type:
        raise ValueError("The URL did not return an HTML page.")
    return extract_page(response.text, final_url)


def fetch_page(url: str) -> str:
    """Fetch one public HTML page and return its readable text."""
    return _fetch_document(url)[0]


def crawl_site(start_url: str, max_pages: int = DEFAULT_MAX_PAGES) -> list[tuple[str, str]]:
    """Read bounded, same-domain HTML pages starting from start_url."""
    if not 1 <= max_pages <= MAX_ALLOWED_PAGES:
        raise ValueError(f"max_pages must be between 1 and {MAX_ALLOWED_PAGES}.")
    start_url = _public_url(start_url)
    domain = urlparse(start_url).hostname.lower()
    queue = deque([start_url])
    visited = set()
    pages = []
    total_chars = 0
    while queue and len(pages) < max_pages and total_chars < MAX_TOTAL_CHARS:
        url = queue.popleft()
        normalized, _ = urldefrag(url)
        if normalized in visited:
            continue
        visited.add(normalized)
        text, links = _fetch_document(normalized)
        if text:
            remaining = MAX_TOTAL_CHARS - total_chars
            text = text[:remaining]
            pages.append((normalized, text))
            total_chars += len(text)
        for link in links:
            parsed = urlparse(link)
            if parsed.hostname and parsed.hostname.lower() == domain and link not in visited:
                queue.append(link)
    if not pages:
        raise ValueError("No readable HTML pages were found.")
    return pages


@st.cache_data(show_spinner=False, ttl=300)
def cached_crawl_site(start_url: str, max_pages: int) -> list[tuple[str, str]]:
    return crawl_site(start_url, max_pages)


def build_prompt(
    sources: list[tuple[str, str]], task: str, criteria: str
) -> str:
    source_text = "\n\n".join(
        f"### Source {index}: {url}\n{content}"
        for index, (url, content) in enumerate(sources, start=1)
    )
    source_text = source_text[:MAX_PROMPT_CHARS]
    return f"""Compare the following website content for the user's task.

Task: {task.strip()}
Comparison criteria: {criteria.strip()}

Use only the supplied content. Cite the exact source URL for every important
claim. Do not invent facts. Clearly identify unavailable, uncertain, or
conflicting information. Return:
1. A concise result for each source
2. A cross-check table with confidence levels
3. A ranked comparison with trade-offs
4. One recommendation and limitations

{source_text}"""


def compare_sources(
    sources: list[tuple[str, str]], task: str, criteria: str, api_key: str
) -> str:
    if not sources or not task.strip() or not criteria.strip():
        raise ValueError("Sources, task, and comparison criteria are required.")
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        input=build_prompt(sources, task, criteria),
    )
    return response.output_text


def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except (FileNotFoundError, KeyError):
        return ""


def _password_gate() -> bool:
    configured = _secret("APP_PASSWORD")
    if not configured:
        st.error("APP_PASSWORD is not configured in Streamlit secrets.")
        return False
    if st.session_state.get("authenticated"):
        return True
    entered = st.text_input("App password", type="password")
    if st.button("Unlock"):
        if hashlib.sha256(entered.encode()).digest() == hashlib.sha256(
            configured.encode()
        ).digest():
            st.session_state.authenticated = True
            st.rerun()
        st.error("Incorrect password.")
    return False


def main() -> None:
    st.set_page_config(page_title="Multi-Website AI Research", page_icon="🔎")
    st.title("🔎 Multi-Website AI Research")
    if not _password_gate():
        st.stop()

    st.write("Compare information from four or five public websites using an AI model.")
    with st.sidebar:
        st.header("Configuration")
        api_key = st.text_input(
            "OpenAI API key",
            value=_secret("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
            type="password",
        )
        max_pages = st.slider(
            "Pages per website", 1, MAX_ALLOWED_PAGES, DEFAULT_MAX_PAGES
        )
        st.caption("Only same-domain HTML pages are crawled.")

    urls = []
    for index in range(5):
        value = st.text_input(
            f"Website URL {index + 1}{' (required)' if index < 4 else ' (optional)'}",
            placeholder="https://example.com",
        ).strip()
        if value:
            urls.append(value)
    task = st.text_area("Task", placeholder="What should be found on every website?")
    criteria = st.text_area(
        "Comparison criteria", placeholder="How should the results be ranked?"
    )

    if st.button("Analyze websites", type="primary"):
        if len(urls) < 4:
            st.error("Enter at least four website URLs.")
            return
        if len(set(urls)) != len(urls):
            st.error("Each website URL must be unique.")
            return
        if not api_key:
            st.error("Provide an OpenAI API key in the sidebar or Streamlit secrets.")
            return
        if not task.strip() or not criteria.strip():
            st.error("Provide both a task and comparison criteria.")
            return

        sources = []
        failures = []
        with st.spinner("Reading websites and preparing the comparison..."):
            for url in urls:
                try:
                    sources.extend(cached_crawl_site(url, max_pages))
                except (requests.RequestException, ValueError) as error:
                    failures.append(f"{url}: {error}")
        for failure in failures:
            st.warning(f"Could not read {failure}")
        if len(sources) < 4:
            st.error("At least four readable website pages are required.")
            return
        try:
            result = compare_sources(sources, task, criteria, api_key)
        except (APIError, ValueError) as error:
            st.error(f"The AI comparison failed: {error}")
            return
        st.subheader("Comparison")
        st.markdown(result)
        st.download_button(
            "Download comparison",
            result,
            file_name="website-comparison.md",
            mime="text/markdown",
        )


if __name__ == "__main__":
    main()
