_DAILY_MESSAGES = {
    "processing": "AI health analysis is being generated.",
    "not_enough_data": "Not enough health data to generate today's insight.",
    "failed": "AI health analysis failed to generate.",
}


def status_message(status_: str, range_: str) -> str | None:
    if status_ == "ready":
        return None
    if range_ == "daily":
        return _DAILY_MESSAGES.get(status_)
    label = range_.capitalize()
    return {
        "processing": f"{label} health report is being generated.",
        "not_enough_data": "Not enough health data to generate this report.",
        "failed": f"{label} health report generation failed.",
    }.get(status_)
