"""
wallet_adapters -- MetaMask wallet integration extracted from ai_base.

This package re-exports every public symbol so that existing imports such as::

    from apps.ui_automation.ai_base import MetaMaskWalletController

continue to work unchanged (ai_base re-imports from here).
"""

# ---- selectors ----
from .selectors import (
    BOOTSTRAP_PLACEHOLDER_TAB_URLS,
    METAMASK_CONNECT_CONFIRM_SELECTOR,
    METAMASK_CONNECT_TEXT_BUTTONS,
    METAMASK_CONFIRM_TEXT_BUTTONS,
    METAMASK_FOOTER_CONFIRM_SELECTOR,
    METAMASK_UNLOCK_PASSWORD_SELECTOR,
    METAMASK_UNLOCK_SUBMIT_SELECTOR,
    METAMASK_UNLOCK_TEXT_BUTTONS,
    is_bootstrap_placeholder_tab_url,
)

# ---- chains ----
from .chains import (
    WALLET_TARGET_CHAIN_PRESETS,
    _normalize_wallet_chain_alias,
    _normalize_wallet_chain_id,
    resolve_wallet_target_chain_config,
)

# ---- url_extraction ----
from .url_extraction import (
    _ORIGINAL_BROWSER_USE_EXTRACT_START_URL,
    _fallback_extract_start_url_from_task,
    extract_browser_use_start_url_from_task,
    sanitize_task_text_for_browser_url_extraction,
)

# ---- prompt_rules ----
from .prompt_rules import build_wallet_mode_rules

# ---- task_detection ----
from .task_detection import (
    BUSINESS_BLOCKER_SIGNAL_RULES,
    TRADE_TASK_MARKERS,
    _normalize_wallet_task_text,
    _task_has_trade_intent,
    _task_requires_target_chain,
    _task_requires_wallet_connection,
    detect_business_blocker_for_active_task,
    detect_business_blocker_signal,
    validate_wallet_task_completion_state,
)

# ---- page_actions ----
from .page_actions import (
    _build_selector_candidates,
    _click_first_available_locator,
    _fill_first_available_locator,
    _is_metamask_blocking_auth_step,
    _is_metamask_provider_selection_step,
    _is_metamask_unlock_step,
    _pick_button_text_selector,
    _selectors_still_visible,
    _strip_html_text_preview,
    _wait_for_first_visible_locator,
    _wait_for_metamask_page_transition,
    inspect_metamask_page_html,
)

# ---- snapshot ----
from .snapshot import (
    _collect_metamask_snapshots,
    _ensure_metamask_home_page,
    inspect_metamask_pages_action,
    select_metamask_snapshot,
)

# ---- metamask (controller + action wrappers) ----
from .metamask import (
    MetaMaskWalletController,
    _with_metamask_pages,
    build_wallet_debugger_http_url,
    perform_metamask_confirm_action,
    perform_metamask_ensure_target_chain_action,
    perform_metamask_unlock_action,
    probe_metamask_wallet_runtime,
    reorder_wallet_planned_steps,
)

# ---- recovery ----
from .recovery import (
    _body_text_has_wallet_picker,
    _fetch_target_body_text,
    _get_browser_session_target_url,
    _normalize_wallet_recovery_url,
    activate_browser_session_focus_target,
    navigate_browser_session_via_new_target,
    recover_empty_wallet_dapp_tab,
    reload_browser_session_focus_target,
    should_fallback_navigation_with_new_target,
    should_open_url_in_new_target,
    stabilize_browser_session_initial_focus,
)

__all__ = [
    # selectors
    'BOOTSTRAP_PLACEHOLDER_TAB_URLS',
    'METAMASK_CONNECT_CONFIRM_SELECTOR',
    'METAMASK_CONNECT_TEXT_BUTTONS',
    'METAMASK_CONFIRM_TEXT_BUTTONS',
    'METAMASK_FOOTER_CONFIRM_SELECTOR',
    'METAMASK_UNLOCK_PASSWORD_SELECTOR',
    'METAMASK_UNLOCK_SUBMIT_SELECTOR',
    'METAMASK_UNLOCK_TEXT_BUTTONS',
    'is_bootstrap_placeholder_tab_url',
    # chains
    'WALLET_TARGET_CHAIN_PRESETS',
    '_normalize_wallet_chain_alias',
    '_normalize_wallet_chain_id',
    'resolve_wallet_target_chain_config',
    # url_extraction
    '_ORIGINAL_BROWSER_USE_EXTRACT_START_URL',
    '_fallback_extract_start_url_from_task',
    'extract_browser_use_start_url_from_task',
    'sanitize_task_text_for_browser_url_extraction',
    # prompt_rules
    'build_wallet_mode_rules',
    # task_detection
    'BUSINESS_BLOCKER_SIGNAL_RULES',
    'TRADE_TASK_MARKERS',
    '_normalize_wallet_task_text',
    '_task_has_trade_intent',
    '_task_requires_target_chain',
    '_task_requires_wallet_connection',
    'detect_business_blocker_for_active_task',
    'detect_business_blocker_signal',
    'validate_wallet_task_completion_state',
    # page_actions
    '_build_selector_candidates',
    '_click_first_available_locator',
    '_fill_first_available_locator',
    '_is_metamask_blocking_auth_step',
    '_is_metamask_provider_selection_step',
    '_is_metamask_unlock_step',
    '_pick_button_text_selector',
    '_selectors_still_visible',
    '_strip_html_text_preview',
    '_wait_for_first_visible_locator',
    '_wait_for_metamask_page_transition',
    'inspect_metamask_page_html',
    # snapshot
    '_collect_metamask_snapshots',
    '_ensure_metamask_home_page',
    'inspect_metamask_pages_action',
    'select_metamask_snapshot',
    # metamask
    'MetaMaskWalletController',
    '_with_metamask_pages',
    'build_wallet_debugger_http_url',
    'perform_metamask_confirm_action',
    'perform_metamask_ensure_target_chain_action',
    'perform_metamask_unlock_action',
    'probe_metamask_wallet_runtime',
    'reorder_wallet_planned_steps',
    # recovery
    '_body_text_has_wallet_picker',
    '_fetch_target_body_text',
    '_get_browser_session_target_url',
    '_normalize_wallet_recovery_url',
    'activate_browser_session_focus_target',
    'navigate_browser_session_via_new_target',
    'recover_empty_wallet_dapp_tab',
    'reload_browser_session_focus_target',
    'should_fallback_navigation_with_new_target',
    'should_open_url_in_new_target',
    'stabilize_browser_session_initial_focus',
]
