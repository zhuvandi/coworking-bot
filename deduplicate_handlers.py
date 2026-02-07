import re
from pathlib import Path

SOURCE = Path("/home/coworkingbot/working_bot_fixed.py")
TARGET = Path("/home/coworkingbot/working_bot_fixed_clean.py")

TEXT = SOURCE.read_text(encoding="utf-8")

# --- правила дублей ---
DUPLICATE_COMMANDS = [
    r'@dp\.message\(Command\("help"\)\)',
    r'@dp\.message\(Command\("stats"\)\)',
]

def remove_duplicates(text: str, pattern: str) -> str:
    matches = list(re.finditer(pattern, text))
    if len(matches) <= 1:
        return text  # дублей нет

    # оставляем первое, остальные вырезаем
    for m in matches[1:]:
        start = m.start()
        # ищем конец функции
        func_end = text.find("\n\n", start)
        if func_end == -1:
            func_end = len(text)
        text = text[:start] + text[func_end:]

    return text


for pattern in DUPLICATE_COMMANDS:
    TEXT = remove_duplicates(TEXT, pattern)

TARGET.write_text(TEXT, encoding="utf-8")

print("OK: дубли удалены")
print("Создан файл:", TARGET)
