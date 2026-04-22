TERMINAL_TASK_STATUSES = {'completed', 'failed', 'skipped'}
ACTIVE_TASK_STATUSES = {'pending', 'in_progress'}


def update_planned_task_status(planned_tasks, task_id, task_status):
    """Update a task in-place and report whether a matching task was found."""
    if not planned_tasks or task_id is None or not task_status:
        return False

    normalized_status = str(task_status).strip().lower()
    for task in planned_tasks:
        if str(task.get('id')) == str(task_id):
            task['status'] = normalized_status
            return True
    return False


def backfill_prior_pending_tasks(planned_tasks, current_task_id):
    """Backfill only tightly dependent prior tasks that were obviously completed."""
    if not planned_tasks or current_task_id is None:
        return []

    try:
        current_task_id_int = int(current_task_id)
    except (TypeError, ValueError):
        return []

    task_by_id = {}
    for task in planned_tasks:
        try:
            task_by_id[int(task.get('id'))] = task
        except (TypeError, ValueError):
            continue

    current_task = task_by_id.get(current_task_id_int)
    previous_task = task_by_id.get(current_task_id_int - 1)
    if not current_task or not previous_task:
        return []

    if previous_task.get('status', 'pending') not in ACTIVE_TASK_STATUSES:
        return []

    previous_desc = str(previous_task.get('description', '')).strip()
    current_desc = str(current_task.get('description', '')).strip()

    verification_keywords = ['校验', '确认', '检查', '验证', '断言']
    if any(keyword in previous_desc for keyword in verification_keywords):
        return []

    dependency_pairs = [
        (['访问', '打开', '进入'], ['搜索', '输入', '点击', '查看']),
        (['搜索'], ['点击第', '点击第1条', '点击第二条', '查看详情']),
        (['点击第', '点击第1条', '点击第二条', '查看详情'], ['关闭', '关闭该标签页', '关闭标签页']),
        (['打开详情', '查看详情'], ['关闭', '返回']),
    ]

    def matches_any(text, keywords):
        return any(keyword in text for keyword in keywords)

    allowed = any(
        matches_any(previous_desc, prev_keywords) and matches_any(current_desc, curr_keywords)
        for prev_keywords, curr_keywords in dependency_pairs
    )
    if not allowed:
        return []

    previous_task['status'] = 'completed'
    return [current_task_id_int - 1]


def sync_planned_task_status(planned_tasks, task_id, task_status):
    """Mirror a task status update into the local task list used by the agent loop."""
    normalized_status = str(task_status or '').strip().lower()
    backfilled_task_ids = []
    if normalized_status == 'completed':
        backfilled_task_ids = backfill_prior_pending_tasks(planned_tasks, task_id)
    updated = update_planned_task_status(planned_tasks, task_id, normalized_status)
    return {
        'updated': updated,
        'backfilled_task_ids': backfilled_task_ids,
    }


def get_next_active_task(planned_tasks, active_statuses=None):
    if not planned_tasks:
        return None

    active = set(active_statuses or ACTIVE_TASK_STATUSES)
    for task in planned_tasks:
        if task.get('status', 'pending') in active:
            return task
    return None
