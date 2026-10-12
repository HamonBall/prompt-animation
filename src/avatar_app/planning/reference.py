"""Opt-in public web context. Fetch only the URL the user explicitly supplies."""
from html.parser import HTMLParser
import ipaddress
import socket
import urllib.parse
import urllib.request
from ..models import PlanError
from .local_model import NoRedirect


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'nav', 'footer'):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'nav', 'footer'):
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


def load_reference(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and parsed.port in (None, 443)
    except ValueError:
        valid = False
    if not valid:
        raise PlanError('Reference URL must be a public HTTPS page without credentials.')
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise PlanError('References must use public internet addresses.')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(url, headers={'User-Agent': 'AvatarAnimation/0.2'})
        with opener.open(request, timeout=12) as response:
            content_type = response.headers.get_content_type()
            if content_type not in ('text/html', 'text/plain'):
                raise PlanError('Use an HTML or plain-text reference page.')
            raw = response.read(200001)
            if len(raw) > 200000:
                raise PlanError('Reference page is too large; use a shorter page.')
            text = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        if content_type == 'text/html':
            parser = PageText()
            parser.feed(text)
            text = ' '.join(parser.parts)
        text = ' '.join(text.split())[:3000]
        if not text:
            raise PlanError('The reference page contains no readable text.')
        return {'url': url, 'text': text}
    except (OSError, ValueError) as exc:
        if isinstance(exc, PlanError):
            raise
        raise PlanError('Could not load the reference page. Previous animation kept.') from exc
