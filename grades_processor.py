import pandas as pd
import re
from pathlib import Path

# Регулярка для поиска ФИО на казахском / русском
NAME_RE = re.compile(r'^[А-ЯӘІҢҒҮҰӨЁ][а-яәіңғүұөё\-]+(?:\s+[А-ЯӘІҢҒҮҰӨЁ][а-яәіңғүұөё\-]+)+$', re.UNICODE)
def allowed_file(filename, allowed_extensions={'csv', 'xlsx'}):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
def process_grades_file(file_path):
    """
    Умный парсер Excel/CSV.
    Работает с файлами из Kundelik и BilimKlass.
    Автоматически ищет имена, считает средний балл и рейтинг.
    Возвращает DataFrame с ['name','class','average','place','korean_rating'].
    """
    path = Path(file_path)
    xls = pd.ExcelFile(path)
    sheet = xls.sheet_names[0]
    raw = pd.read_excel(xls, sheet_name=sheet, header=None)

    # 1️⃣ Найдём колонку, где чаще всего встречаются ФИО
    col_scores = []
    for ci in range(raw.shape[1]):
        col = raw.iloc[:, ci].astype(str).fillna("")
        matches = col.str.match(NAME_RE)
        col_scores.append((ci, matches.sum()))
    col_scores.sort(key=lambda x: x[1], reverse=True)
    name_col_idx = col_scores[0][0]

    # 2️⃣ Найдём строку, где начинается список учеников
    first_name_row = None
    for i in range(raw.shape[0]):
        cell = raw.iat[i, name_col_idx]
        if isinstance(cell, str) and NAME_RE.match(cell):
            first_name_row = i
            break
    if first_name_row is None:
        first_name_row = 0

    # 3️⃣ Очищаем данные и переименовываем колонки
    clean = raw.iloc[first_name_row:, :].copy().reset_index(drop=True)
    clean.columns = [f"col_{i}" for i in range(clean.shape[1])]
    clean = clean.rename(columns={f"col_{name_col_idx}": "name"})

    # 4️⃣ Ищем числовые колонки (оценки)
    numeric_cols = []
    for c in clean.columns:
        if c == "name":
            continue
        coer = pd.to_numeric(clean[c], errors="coerce")
        if coer.dropna().shape[0] >= max(3, int(0.25 * clean.shape[0])):  # минимум 25% чисел
            numeric_cols.append(c)

    # 5️⃣ Считаем средний балл
    clean["average"] = clean[numeric_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)

    # 6️⃣ Формируем таблицу
    result = pd.DataFrame()
    result["name"] = clean["name"]
    # Попробуем найти колонку "Класс" (если есть)
    class_candidates = [c for c in clean.columns if any(k in str(c).lower() for k in ["класс", "сынып", "class"])]
    result["class"] = clean[class_candidates[0]] if class_candidates else None
    result["average"] = pd.to_numeric(clean["average"], errors="coerce").fillna(0).astype(float)

    # 7️⃣ Сортировка и рейтинг
    result = result.sort_values("average", ascending=False).reset_index(drop=True)
    result["place"] = result.index + 1
    total = len(result)

    def korean_rating(rank):
        p = ((rank - 1) / total) * 100  # исправлено
        if p < 4: return 1
        if p < 11: return 2
        if p < 23: return 3
        if p < 40: return 4
        if p < 60: return 5
        if p < 77: return 6
        if p < 89: return 7
        if p < 96: return 8
        return 9

    result["korean_rating"] = result["place"].apply(korean_rating)
    return result[["name", "class", "average", "place", "korean_rating"]]
