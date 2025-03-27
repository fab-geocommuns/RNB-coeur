def create_all_bal_links_tasks(dpts: list):

    tasks = []

    for dpt in dpts:
        dpt_tasks = _create_bal_links_dpt_tasks(dpt)
        tasks.extend(dpt_tasks)

    return tasks
