"""Bounded, repository-bound GitHub GET transport. No automatic credential discovery or retries."""
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .publication_contract import REPOSITORY, canonical, require, require_remote


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class GitHubAPI:
    def __init__(self, token=None, opener=None):
        self.token = token
        self.opener = opener or build_opener(NoRedirect()).open

    def __call__(self, method, path, payload=None, *, binary=False):
        if method != 'GET':
            require_remote()  # Default cannot be armed by a flag or environment variable.
        require(path.startswith(('/git/', '/compare/', '/releases', '/pages/deployments', '/actions/runs/')) and
                '..' not in path and '://' not in path and '\\' not in path, 'Repository API path not allowed')
        url = 'https://api.github.com/repos/'+REPOSITORY+path
        headers = {'Accept':'application/octet-stream' if binary else 'application/vnd.github+json',
                   'X-GitHub-Api-Version':'2026-03-10', 'User-Agent':'tw-market-scanner-read-only'}
        if self.token:
            headers['Authorization'] = 'Bearer '+self.token
        request = Request(url, headers=headers, method='GET')
        try:
            response = self.opener(request, timeout=15)
        except HTTPError as exc:
            if not binary or exc.code != 302:
                raise  # 403/429, unknown errors and GET timeouts never retry.
            target = exc.headers.get('Location', ''); parsed = urlsplit(target)
            require(parsed.scheme == 'https' and parsed.hostname in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com') and
                    not parsed.username and not parsed.password, 'Unapproved asset redirect')
            # Signed asset request receives no Authorization or cookies.
            response = self.opener(Request(target, headers={'Accept':'application/octet-stream'}), timeout=15)
        limit = 64*1024*1024 if binary else 16*1024*1024
        with response:
            body = response.read(limit+1)
            require(response.status == 200 and len(body) <= limit, 'GitHub response status/size')
        return body if binary else json.loads(body)
