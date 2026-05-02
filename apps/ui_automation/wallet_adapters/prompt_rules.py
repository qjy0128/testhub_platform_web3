import logging

logger = logging.getLogger(__name__)


def build_wallet_mode_rules(wallet_provider, target_chain):
    provider_label = str(wallet_provider or 'metamask')
    chain_label = str(target_chain or 'unspecified')
    return (
        "\nWALLET MODE RULES:\n"
        f"- This run uses a real Chrome profile with {provider_label} already installed.\n"
        f"- Target chain: {chain_label}.\n"
        "- Handle wallet tasks in this order when the dApp triggers them: connect wallet, switch chain, sign message, confirm transaction.\n"
        "- Interact with the dApp first. Some dApps show a generic 'Connect Wallet' entrypoint before the provider list appears. Click that first, then wait for the provider picker.\n"
        "- Wait for the provider picker after clicking 'Connect Wallet'. Do not assume the MetaMask option is visible immediately.\n"
        "- If meaningful text or controls are visible, treat the dApp page as loaded. Do not keep waiting or call done just because the layout changed.\n"
        "- If the dApp page looks correct but the body stays empty, skeleton-only, or otherwise half-loaded, recover by returning focus to a fresh foreground tab and retry the current dApp step once before failing.\n"
        "- When a MetaMask popup/tab opens, switch to it and finish the approval before returning to the dApp.\n"
        "- browser-use cannot reliably inspect chrome-extension pages in this environment. Use the dedicated MetaMask actions instead of generic clicks inside the extension.\n"
        "- If MetaMask opens an unlock page (#/unlock or home.html#unlock), call metamask_unlock with the provided password before any wallet approval step.\n"
        "- If MetaMask opens a connect, signature, chain switch, or transaction confirmation page, call metamask_confirm to press the primary approval button.\n"
        "- If the dApp must run on the configured target chain, call metamask_ensure_target_chain after the dApp page is visible instead of manually hunting MetaMask network controls.\n"
        "- If the current MetaMask state is unclear, call metamask_inspect before failing.\n"
        "- NEVER skip, fake, or silently bypass wallet approval steps.\n"
        "- NEVER fall back to blind generic clicking inside MetaMask before the popup/tab is clearly visible.\n"
        "- If MetaMask does not appear after the dApp action, stop and mark the current wallet-related sub-task as failed.\n"
    )
