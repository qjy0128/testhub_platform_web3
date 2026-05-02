import logging
import re

logger = logging.getLogger(__name__)

WALLET_TARGET_CHAIN_PRESETS = (
    {
        'aliases': {
            'bnb smart chain testnet',
            'bnb chain testnet',
            'bsc testnet',
            'binance smart chain testnet',
            '0x61',
            '97',
        },
        'chain_id': '0x61',
        'chain_name': 'BNB Smart Chain Testnet',
        'native_currency': {
            'name': 'tBNB',
            'symbol': 'tBNB',
            'decimals': 18,
        },
        'rpc_urls': [
            'https://data-seed-prebsc-1-s1.bnbchain.org:8545',
            'https://data-seed-prebsc-2-s1.bnbchain.org:8545',
        ],
        'block_explorer_urls': [
            'https://testnet.bscscan.com',
        ],
    },
    {
        'aliases': {
            'bnb smart chain',
            'bnb chain',
            'bsc',
            'binance smart chain',
            '0x38',
            '56',
        },
        'chain_id': '0x38',
        'chain_name': 'BNB Smart Chain',
        'native_currency': {
            'name': 'BNB',
            'symbol': 'BNB',
            'decimals': 18,
        },
        'rpc_urls': [
            'https://bsc-dataseed.bnbchain.org',
        ],
        'block_explorer_urls': [
            'https://bscscan.com',
        ],
    },
    {
        'aliases': {
            'ethereum',
            'ethereum mainnet',
            'mainnet',
            '0x1',
            '1',
        },
        'chain_id': '0x1',
        'chain_name': 'Ethereum Mainnet',
        'native_currency': {
            'name': 'Ether',
            'symbol': 'ETH',
            'decimals': 18,
        },
        'rpc_urls': [
            'https://cloudflare-eth.com',
        ],
        'block_explorer_urls': [
            'https://etherscan.io',
        ],
    },
    {
        'aliases': {
            'sepolia',
            'ethereum sepolia',
            'sepolia testnet',
            '0xaa36a7',
            '11155111',
        },
        'chain_id': '0xaa36a7',
        'chain_name': 'Sepolia',
        'native_currency': {
            'name': 'Sepolia Ether',
            'symbol': 'ETH',
            'decimals': 18,
        },
        'rpc_urls': [
            'https://rpc.sepolia.org',
        ],
        'block_explorer_urls': [
            'https://sepolia.etherscan.io',
        ],
    },
)


def _normalize_wallet_chain_alias(value):
    normalized = str(value or '').strip().lower()
    if not normalized:
        return ''
    return re.sub(r'\s+', ' ', normalized)


def _normalize_wallet_chain_id(value):
    normalized = str(value or '').strip().lower()
    if not normalized:
        return ''
    if normalized.startswith('0x'):
        return normalized
    try:
        return hex(int(normalized))
    except (TypeError, ValueError):
        return normalized


def resolve_wallet_target_chain_config(wallet_context):
    wallet_context = wallet_context or {}
    raw_target_chain = (
        wallet_context.get('wallet_target_chain')
        or wallet_context.get('wallet_target_chain_id')
        or wallet_context.get('target_chain')
        or ''
    )
    normalized_target = _normalize_wallet_chain_alias(raw_target_chain)
    if not normalized_target:
        return None

    for preset in WALLET_TARGET_CHAIN_PRESETS:
        aliases = {_normalize_wallet_chain_alias(alias) for alias in preset.get('aliases', set())}
        if normalized_target in aliases or _normalize_wallet_chain_id(normalized_target) == preset.get('chain_id'):
            chain_config = {
                'chain_id': preset['chain_id'],
                'chain_name': preset['chain_name'],
                'native_currency': dict(preset['native_currency']),
                'rpc_urls': list(preset.get('rpc_urls', [])),
                'block_explorer_urls': list(preset.get('block_explorer_urls', [])),
            }
            chain_config['add_chain_params'] = {
                'chainId': chain_config['chain_id'],
                'chainName': chain_config['chain_name'],
                'nativeCurrency': dict(chain_config['native_currency']),
                'rpcUrls': list(chain_config['rpc_urls']),
                'blockExplorerUrls': list(chain_config['block_explorer_urls']),
            }
            return chain_config

    return None
