from datetime import date


def _next_month(day: date) -> date:
    if day.month == 12:
        return day.replace(year=day.year + 1, month=1)
    return day.replace(month=day.month + 1)


def due_dates(start_date: date, end_date: date | None, due_day: int, through: date) -> list[date]:
    """Dates rent falls due: monthly on due_day, from the first due day on or after
    start_date, up to and including min(through, end_date). due_day is 1-28, so every
    month has it."""
    current = start_date.replace(day=due_day)
    if current < start_date:
        current = _next_month(current)
    last = min(through, end_date) if end_date is not None else through
    dates = []
    while current <= last:
        dates.append(current)
        current = _next_month(current)
    return dates
