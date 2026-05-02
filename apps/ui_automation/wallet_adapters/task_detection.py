import logging
import re
from urllib.parse import urlsplit

from .chains import (
    _normalize_wallet_chain_alias,
    _normalize_wallet_chain_id,
    resolve_wallet_target_chain_config,
)

logger = logging.getLogger(__name__)

TRADE_TASK_MARKERS = (
    'swap',
    'trade',
    'buy',
    'sell',
    'exchange',
    'launchpad',
    '发射台',
    '兑换',
    '换币',
    '买入',
    '卖出',
    '购买',
    '出售',
)

BUSINESS_BLOCKER_SIGNAL_RULES = (
    {
        'code': 'price_impact_too_high',
        'message': '当前交易报价价格影响过高，站点已阻止继续执行',
        'keywords': (
            'price impact too high',
            '价格影响过高',
        ),
    },
    {
        'code': 'routing_timeout',
        'message': '当前交易报价路由超时，页面未返回可执行报价',
        'keywords': (
            'routing timeout',
            '路由超时',
        ),
    },
    {
        'code': 'insufficient_liquidity',
        'message': '当前币对流动性不足或没有可执行路由',
        'keywords': (
            'insufficient liquidity',
            '流动性不足',
            'no route found',
            '无法找到路由',
            '无可用路由',
        ),
    },
)


def _normalize_wallet_task_text(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _task_requires_wallet_connection(task_description):
    normalized = _normalize_wallet_task_text(task_description)
    if not normalized:
        return False
    return any(
        marker in normalized
        for marker in (
            'connect wallet',
            '连接钱包',
            '连接 metamask',
            '连接 meta mask',
            '连接 meta-mask',
            '使用 metamask 连接',
            'use metamask',
        )
    )


def _task_requires_target_chain(task_description, target_chain_config=None):
    normalized = _normalize_wallet_task_text(task_description)
    if not normalized:
        return False

    has_chain_intent = any(
        marker in normalized
        for marker in ('switch chain', 'target chain', 'network', 'chain', '切链', '切换网络', '目标链', '网络')
    )
    if not has_chain_intent:
        return False

    if not target_chain_config:
        return True

    aliases = {
        _normalize_wallet_chain_alias(target_chain_config.get('chain_name')),
        _normalize_wallet_chain_alias(target_chain_config.get('chain_id')),
    }
    for alias in target_chain_config.get('aliases', []) or []:
        aliases.add(_normalize_wallet_chain_alias(alias))
    aliases.discard('')
    return any(alias in normalized for alias in aliases)


def _task_has_trade_intent(task_description):
    normalized = _normalize_wallet_task_text(task_description)
    if not normalized:
        return False
    return any(marker in normalized for marker in TRADE_TASK_MARKERS)


def validate_wallet_task_completion_state(task_description, wallet_context, ethereum_state):
    normalized_task = _normalize_wallet_task_text(task_description)
    if not normalized_task or not (wallet_context or {}).get('enabled'):
        return

    runtime_state = dict(ethereum_state or {})
    has_provider = bool(runtime_state.get('has_provider'))
    current_chain_id = _normalize_wallet_chain_id(runtime_state.get('chain_id'))
    selected_address = str(runtime_state.get('selected_address') or '').strip()

    if _task_requires_wallet_connection(task_description):
        if not has_provider:
            raise RuntimeError('Cannot mark wallet connection task complete before window.ethereum is available')
        if not selected_address:
            raise RuntimeError('Cannot mark wallet connection task complete before the dApp exposes a connected wallet address')

    target_chain_config = resolve_wallet_target_chain_config(wallet_context)
    if target_chain_config and _task_requires_target_chain(task_description, target_chain_config):
        target_chain_id = _normalize_wallet_chain_id(target_chain_config.get('chain_id'))
        if current_chain_id != target_chain_id:
            raise RuntimeError(
                f"Cannot mark target-chain task complete before wallet chain is {target_chain_id}; current chain is {current_chain_id or 'unknown'}"
            )


def detect_business_blocker_signal(text):
    normalized = _normalize_wallet_task_text(text)
    if not normalized:
        return None

    for rule in BUSINESS_BLOCKER_SIGNAL_RULES:
        matched_keyword = next(
            (keyword for keyword in rule.get('keywords', ()) if keyword in normalized),
            None,
        )
        if matched_keyword:
            return {
                'code': rule['code'],
                'message': rule['message'],
                'matched_text': matched_keyword,
            }
    return None


async def detect_business_blocker_for_active_task(
    browser_session,
    task_description,
    target_id=None,
    body_text_fetcher=None,
    tabs=None,
):
    from .recovery import _fetch_target_body_text, _get_browser_session_target_url

    if not _task_has_trade_intent(task_description):
        return None

    current_target_id = target_id or getattr(browser_session, 'agent_focus_target_id', None)
    if not current_target_id:
        return None

    current_url = _get_browser_session_target_url(browser_session, current_target_id, tabs=tabs)
    split_result = urlsplit(str(current_url or '').strip())
    if split_result.scheme.lower() not in {'http', 'https'} or not split_result.netloc:
        return None

    fetch_body_text = body_text_fetcher or _fetch_target_body_text
    current_body_text = str(await fetch_body_text(browser_session, current_target_id) or '').strip()
    if not current_body_text:
        return None

    blocker = detect_business_blocker_signal(current_body_text)
    if not blocker:
        return None

    return {
        **blocker,
        'url': current_url,
        'target_id': current_target_id,
    }
