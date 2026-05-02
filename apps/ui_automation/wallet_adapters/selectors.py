import logging

logger = logging.getLogger(__name__)

# MetaMask test-id based selectors
METAMASK_UNLOCK_PASSWORD_SELECTOR = '[data-testid="unlock-password"]'
METAMASK_UNLOCK_SUBMIT_SELECTOR = '[data-testid="unlock-submit"]'
METAMASK_CONNECT_CONFIRM_SELECTOR = '[data-testid="confirm-btn"]'
METAMASK_FOOTER_CONFIRM_SELECTOR = '[data-testid="confirm-footer-button"]'

# MetaMask text button labels
METAMASK_UNLOCK_TEXT_BUTTONS = ['Unlock', '解锁', '登录']
METAMASK_CONNECT_TEXT_BUTTONS = ['Connect', '连接', '下一步', 'Next']
METAMASK_CONFIRM_TEXT_BUTTONS = [
    'Confirm', '确认', 'Approve', '签名', '切换网络',
    'Switch network', 'Send',
]

# Bootstrap placeholder tab URLs used to detect Chrome/Edge internal new-tab pages
BOOTSTRAP_PLACEHOLDER_TAB_URLS = {
    'chrome://newtab-footer',
    'chrome://newtab-footer/',
    'chrome://newtab',
    'chrome://newtab/',
    'chrome://new-tab-page',
    'chrome://new-tab-page/',
    'edge://newtab',
    'edge://newtab/',
}


def is_bootstrap_placeholder_tab_url(url):
    normalized = str(url or '').strip().lower()
    return normalized in BOOTSTRAP_PLACEHOLDER_TAB_URLS
