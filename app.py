import ipaddress
import os
import socket
from urllib.parse import urlparse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI


MAX_PAGE_CHARS = 12_000


def _public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are supported.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise ValueError("The website hostname could not be resolved.") from None
    if not all(
        not ipaddress.ip_address(item[4][0]).is_private
        and not ipaddress.ip_address(item[4][0]).is_loopback
        and not ipaddress.ip_address(item[4][0]).is_link_local
        for item in addresses
    ):
        raise ValueError("Only public HTTP(S) URLs are supported.")
    return url


def fetch_page(url: str) -> str:
    safe_url = _public_url(url)
    response = requests.get(  # lgtm[py/full-ssrf]
        safe_url,
        headers={"User-Agent": "MultiWebsiteResearch/1.0"},
        timeout=15,
        allow_redirects=True,
    )
    response.raise_for_status()
    _public_url(response.url)
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    text = " ".join(soup.stripped_strings)
    return text[:MAX_PAGE_CHARS]


def compare_sources(sources: list[tuple[str, str]], task: str, criteria: str, api_key: str) -> str:
    client = OpenAI(api_key=api_key)
    source_text = "\n\n".join(
        f"### Source {index}: {url}\n{content}"
        for index, (url, content) in enumerate(sources, start=1)
    )
    prompt = f"""Compare the following website content for the user's task.

Task: {task}
Comparison criteria: {criteria}

Use only the supplied content. Cite the source URL for every important claim,
identify conflicts or missing information, and do not invent facts. Return:
1. A concise result for each source
2. A cross-check table with confidence levels
3. A ranked comparison with trade-offs
4. One recommendation and limitations

{source_text}"""
    response = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
    )
    return response.output_text


st.set_page_config(page_title="Multi-Website AI Research", page_icon="🔎")
st.title("🔎 Multi-Website AI Research")
st.write("Compare information from four or five public websites using an AI model.")

with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input(
        "OpenAI API key",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
        help="Used only for this request and never displayed.",
    )
    model_note = "The app uses gpt-4o-mini for the comparison."
    st.caption(model_note)

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
    "Comparison criteria",
    placeholder="How should the results be ranked or compared?",
)

if st.button("Analyze websites", type="primary"):
    if len(urls) < 4:
        st.error("Enter at least four website URLs.")
    elif not api_key:
        st.error("Provide an OpenAI API key in the sidebar or OPENAI_API_KEY.")
    elif not task.strip() or not criteria.strip():
        st.error("Provide both a task and comparison criteria.")
    elif len(set(urls)) != len(urls):
        st.error("Each website URL must be unique.")
    else:
        sources = []
        with st.spinner("Reading websites and preparing the comparison..."):
            for url in urls:
                try:
                    sources.append((url, fetch_page(url)))
                except (requests.RequestException, ValueError) as error:
                    st.warning(f"Could not read {url}: {error}")
        if len(sources) < 4:
            st.error("At least four websites must be accessible to run the comparison.")
        else:
            try:
                result = compare_sources(sources, task, criteria, api_key)
                st.subheader("Comparison")
                st.markdown(result)
            except Exception as error:
                st.error(f"The AI comparison failed: {error}")
