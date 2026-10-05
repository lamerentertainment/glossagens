import base64
import os
import re

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO = os.getenv("GITHUB_REPO", "glossagens/glossagens")
BASE_URL = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _r(method: str, path: str, **kwargs) -> dict:
    url = f"{BASE_URL}{path}"
    resp = requests.request(method, url, headers=_headers(), **kwargs)
    resp.raise_for_status()
    return resp.json() if resp.content else {}


# ── Content ──────────────────────────────────────────────────────────────────

def get_file(path: str, branch: str = "main") -> tuple[str, str]:
    """Returns (content, sha) for an existing file."""
    data = _r("GET", f"/repos/{REPO}/contents/{path}", params={"ref": branch})
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def create_or_update_file(path: str, content: str, message: str, branch: str = "main"):
    """Creates or updates a file directly on branch."""
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {"message": message, "content": encoded, "branch": branch}
    try:
        _, sha = get_file(path, branch)
        payload["sha"] = sha
    except requests.HTTPError:
        pass  # new file
    _r("PUT", f"/repos/{REPO}/contents/{path}", json=payload)


def create_branch(branch: str, from_branch: str = "main"):
    ref = _r("GET", f"/repos/{REPO}/git/ref/heads/{from_branch}")
    sha = ref["object"]["sha"]
    _r("POST", f"/repos/{REPO}/git/refs", json={
        "ref": f"refs/heads/{branch}",
        "sha": sha,
    })


# ── Pull Requests ─────────────────────────────────────────────────────────────

def create_pr(title: str, body: str, head: str, base: str = "main") -> int:
    data = _r("POST", f"/repos/{REPO}/pulls", json={
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    })
    return data["number"]


def merge_pr(pr_number: int, message: str = ""):
    _r("PUT", f"/repos/{REPO}/pulls/{pr_number}/merge", json={
        "merge_method": "squash",
        "commit_message": message,
    })


def close_pr(pr_number: int):
    _r("PATCH", f"/repos/{REPO}/pulls/{pr_number}", json={"state": "closed"})


def get_pr_diff(pr_number: int) -> str:
    url = f"{BASE_URL}/repos/{REPO}/pulls/{pr_number}"
    resp = requests.get(url, headers={**_headers(), "Accept": "application/vnd.github.diff"})
    resp.raise_for_status()
    return resp.text


# ── Issues ────────────────────────────────────────────────────────────────────

def comment_issue(issue_number: int, body: str):
    _r("POST", f"/repos/{REPO}/issues/{issue_number}/comments", json={"body": body})


def close_issue(issue_number: int):
    _r("PATCH", f"/repos/{REPO}/issues/{issue_number}", json={"state": "closed"})


def create_issue(title: str, body: str, labels: list[str]) -> dict:
    return _r("POST", f"/repos/{REPO}/issues", json={
        "title": title,
        "body": body,
        "labels": labels,
    })


def list_dir(path: str, branch: str = "main") -> list[dict]:
    return _r("GET", f"/repos/{REPO}/contents/{path}", params={"ref": branch})


def search_code(query: str, limit: int = 10) -> list[dict]:
    data = _r("GET", "/search/code", params={
        "q": f"{query} repo:{REPO} path:content/kommentar",
        "per_page": limit,
    })
    return data.get("items", [])


def add_label(issue_number: int, label: str):
    _r("POST", f"/repos/{REPO}/issues/{issue_number}/labels", json={"labels": [label]})


# ── Helpers ───────────────────────────────────────────────────────────────────

def article_path(ref: str) -> str | None:
    """'Art. 1 OR' → 'content/kommentar/or/art-001/_index.md'"""
    m = re.match(r"art\.\s*(\d+)\s+(\w+)", ref.strip(), re.IGNORECASE)
    if not m:
        return None
    nr = int(m.group(1))
    law = m.group(2).lower()
    return f"content/kommentar/{law}/art-{nr:03d}/_index.md"
