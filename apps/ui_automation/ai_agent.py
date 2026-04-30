import asyncio
import logging

from .ai_base import BaseBrowserAgent, normalize_browser_execution_mode

logger = logging.getLogger('django')


class BrowserAgent(BaseBrowserAgent):
    """Browser-use agent wrapper for text and vision execution modes."""

    def __init__(self, execution_mode='text', enable_gif=True, case_name=None, wallet_context=None):
        self.enable_gif = enable_gif
        self.case_name = case_name or 'Adhoc Task'
        super().__init__(
            execution_mode=execution_mode,
            enable_gif=enable_gif,
            case_name=case_name,
            wallet_context=wallet_context,
        )


class TextBrowserAgent(BrowserAgent):
    def __init__(self, execution_mode='text', enable_gif=True, case_name=None, wallet_context=None):
        super().__init__(
            execution_mode='text',
            enable_gif=enable_gif,
            case_name=case_name,
            wallet_context=wallet_context,
        )


class VisionBrowserAgent(BrowserAgent):
    def __init__(self, execution_mode='vision', enable_gif=True, case_name=None, wallet_context=None):
        super().__init__(
            execution_mode='vision',
            enable_gif=enable_gif,
            case_name=case_name,
            wallet_context=wallet_context,
        )


def get_agent_class(execution_mode='text'):
    if normalize_browser_execution_mode(execution_mode) == 'vision':
        return VisionBrowserAgent
    return TextBrowserAgent


def run_ai_task_sync(
    task_description: str,
    planned_tasks=None,
    callback=None,
    should_stop=None,
    execution_mode='text',
    wallet_context=None,
):
    agent_class = get_agent_class(execution_mode)
    agent = agent_class(execution_mode=execution_mode, wallet_context=wallet_context)
    return asyncio.run(agent.run_task(task_description, planned_tasks, callback, should_stop))


def analyze_task_sync(task_description: str, execution_mode='text', wallet_context=None):
    agent_class = get_agent_class(execution_mode)
    agent = agent_class(execution_mode=execution_mode, wallet_context=wallet_context)
    return asyncio.run(agent.analyze_task(task_description))


def run_full_process_sync(
    task_description: str,
    analysis_callback=None,
    step_callback=None,
    should_stop=None,
    execution_mode='text',
    enable_gif=True,
    case_name=None,
    wallet_context=None,
):
    normalized_mode = normalize_browser_execution_mode(execution_mode)
    logger.info(
        'DEBUG: Entering run_full_process_sync with execution_mode=%s, enable_gif=%s',
        normalized_mode,
        enable_gif,
    )

    agent_class = get_agent_class(normalized_mode)
    agent = agent_class(
        execution_mode=normalized_mode,
        enable_gif=enable_gif,
        case_name=case_name,
        wallet_context=wallet_context,
    )

    logger.info('DEBUG: Agent created successfully (%s), starting asyncio.run', type(agent).__name__)
    return asyncio.run(agent.run_full_process(task_description, analysis_callback, step_callback, should_stop))
