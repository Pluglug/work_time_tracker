"""
時間フォーマット用ユーティリティ
"""


def format_time(seconds):
    """
    時間を秒単位から人間が読みやすい形式に変換

    Args:
        seconds (float): 秒数

    Returns:
        str: HH:MM:SS形式の文字列
    """
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_hours_minutes(seconds):
    """
    時間を秒単位から時間と分のみの形式に変換

    Args:
        seconds (float): 秒数

    Returns:
        str: HH:MM形式の文字列
    """
    hours, remainder = divmod(int(seconds), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}"
