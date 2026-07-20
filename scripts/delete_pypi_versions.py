import os
import re
import sys

import requests

TOKEN = os.environ["PYPI_MANAGE_TOKEN"]
PROJECT = "revona"
KEEP = {"1.0.0"}


def main():
    s = requests.Session()
    s.auth = ("", TOKEN)
    s.headers.update({"User-Agent": "revona-cleanup/1.0 (github-actions)"})

    info = s.get(f"https://pypi.org/pypi/{PROJECT}/json", timeout=30).json()
    versions = list(info["releases"].keys())
    to_delete = [v for v in versions if v not in KEEP]
    print(f"all versions: {versions}")
    print(f"will delete: {to_delete}")

    for v in to_delete:
        url = f"https://pypi.org/manage/project/{PROJECT}/release/{v}/"
        r = s.get(url, timeout=30, allow_redirects=False)
        print(f"  [{v}] GET status={r.status_code} loc={r.headers.get('Location','')}")
        if r.status_code in (301, 302, 303) and 'login' in r.headers.get('Location', ''):
            print(f"  [{v}] AUTH FAILED -> redirected to login. Token cannot access web UI.")
            continue
        if "Client Challenge" in r.text:
            print(f"  [{v}] SKIP client challenge")
            continue
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
        if not m:
            print(f"  [{v}] SKIP no csrf_token found")
            continue
        csrf = m.group(1)
        data = {"csrf_token": csrf}
        btn = re.search(r'<button[^>]*name="([^"]+)"[^>]*>Delete', r.text, re.I)
        if btn:
            data[btn.group(1)] = "Delete release"
        resp = s.post(url, data=data, timeout=30, allow_redirects=False)
        print(f"  [{v}] POST delete -> {resp.status_code} loc={resp.headers.get('Location','')}")

    after = s.get(f"https://pypi.org/pypi/{PROJECT}/json", timeout=30).json()
    print(f"remaining versions: {list(after['releases'].keys())}")


if __name__ == "__main__":
    main()
