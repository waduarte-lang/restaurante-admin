from datetime import datetime, timezone, timedelta

_COL = timezone(timedelta(hours=-5))


def colToday() -> str:
    return datetime.now(_COL).strftime("%Y-%m-%d")
