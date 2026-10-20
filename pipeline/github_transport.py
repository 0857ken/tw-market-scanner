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
    def __init__(self, token=None, opener=None, *, capability=None):
        self.token = token
        self.capability = capability
        self.opener = opener or build_opener(NoRedirect()).open

    def __call__(self, method, path, payload=None, *, binary=False):
        if method != 'GET':
            require_remote(self.capability)  # Default cannot be armed by a flag/environment variable.
        require(method in ('GET','POST','PATCH'), 'HTTP mutation verb not supported')
        upload = path.startswith('uploads:')
        relative = path.removeprefix('uploads:')
        require(relative.startswith(('/git/', '/compare/', '/releases', '/pages/deployments', '/actions/runs/', '/actions/artifacts/')) and
                '..' not in relative and '://' not in relative and '\\' not in relative, 'Repository API path not allowed')
        if upload:
            import re
            require(method=='POST' and isinstance(payload,bytes) and
                    re.fullmatch(r'/releases/[0-9]+/assets\?name=[A-Za-z0-9_.%-]+',relative),'Invalid asset upload route')
        require(method!='GET' or payload is None,'GET cannot carry mutable payload')
        require(not relative.startswith('/actions/artifacts/') or method == 'GET', 'Artifact access is read-only')
        url = ('https://uploads.github.com' if upload else 'https://api.github.com')+'/repos/'+REPOSITORY+relative
        headers = {'Accept':'application/octet-stream' if binary else 'application/vnd.github+json',
                   'X-GitHub-Api-Version':'2026-03-10', 'User-Agent':'tw-market-scanner-read-only'}
        if self.token:
            headers['Authorization'] = 'Bearer '+self.token
        body = None
        if payload is not None:
            body = payload if isinstance(payload,bytes) else canonical(payload)
            headers['Content-Type']='application/octet-stream' if isinstance(payload,bytes) else 'application/json'
        request = Request(url, data=body, headers=headers, method=method)
        try:
            response = self.opener(request, timeout=15)
        except HTTPError as exc:
            if method!='GET' or not binary or exc.code != 302:
                raise  # 403/429, unknown errors and GET timeouts never retry.
            target = exc.headers.get('Location', ''); parsed = urlsplit(target)
            artifact_redirect = relative.startswith('/actions/artifacts/') and relative.endswith('/zip') and parsed.hostname and parsed.hostname.endswith('.blob.core.windows.net')
            require(parsed.scheme == 'https' and (parsed.hostname in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com') or artifact_redirect) and
                    parsed.port in (None, 443) and
                    not parsed.username and not parsed.password, 'Unapproved asset redirect')
            # Signed asset request receives no Authorization or cookies.
            response = self.opener(Request(target, headers={'Accept':'application/octet-stream'}), timeout=15)
        limit = 64*1024*1024 if binary else 16*1024*1024
        with response:
            body = response.read(limit+1)
            require(response.status in ((200,) if method=='GET' else (200,201,202)) and len(body) <= limit, 'GitHub response status/size')
        return body if binary else json.loads(body)
