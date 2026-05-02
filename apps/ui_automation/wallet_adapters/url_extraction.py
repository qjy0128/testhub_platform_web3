import logging
import re
from types import SimpleNamespace

logger = logging.getLogger(__name__)

# Module-level reference to the original browser-use URL extractor, set by ai_base
_ORIGINAL_BROWSER_USE_EXTRACT_START_URL = None


def sanitize_task_text_for_browser_url_extraction(task):
    sanitized_task = str(task or '')
    if not sanitized_task:
        return sanitized_task

    # browser-use will treat bare tokens like `home.html#unlock` as a domain and
    # auto-navigate to `https://home.html`. Neutralize those wallet-internal route
    # hints without touching real URLs such as https://example.com/index.html.
    return re.sub(
        r'(?<![\w/:.-])(?P<name>home|notification|popup|background|offscreen|index)\.html(?=(?:[#?)]|\s|$))',
        lambda match: f"{match.group('name')} html",
        sanitized_task,
        flags=re.IGNORECASE,
    )


def _fallback_extract_start_url_from_task(task):
    task_text = str(task or '')
    if not task_text:
        return None

    task_without_emails = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', task_text)
    patterns = [
        r'https?://[^\s<>"\']+',
        r'(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}(?:/[^\s<>"\']*)?',
    ]
    excluded_words = {'never', 'dont', 'not', "don't"}
    found_urls = []

    for pattern in patterns:
        matches = re.finditer(pattern, task_without_emails)
        for match in matches:
            url = re.sub(r'[.,;:!?()\[\]]+$', '', match.group(0))
            context_start = max(0, match.start() - 20)
            context_text = task_without_emails[context_start:match.start()]
            if any(word.lower() in context_text.lower() for word in excluded_words):
                continue
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            found_urls.append(url)

    unique_urls = list(set(found_urls))
    if len(unique_urls) == 1:
        return unique_urls[0]
    return None


def extract_browser_use_start_url_from_task(task, extractor=None, logger_obj=None):
    sanitized_task = sanitize_task_text_for_browser_url_extraction(task)
    extractor_fn = extractor or _ORIGINAL_BROWSER_USE_EXTRACT_START_URL
    if extractor_fn is None:
        return _fallback_extract_start_url_from_task(sanitized_task)

    proxy_self = SimpleNamespace(logger=logger_obj or logger)
    return extractor_fn(proxy_self, sanitized_task)
