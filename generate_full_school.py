import csv
import random

# === НАСТРОЙКИ ===
TEACHERS_COUNT = 170
CLASSES_COUNT = 105  # А-К (10 параллелей)
CORPS = ['А', 'В']  # Два корпуса

# === 1. ГЕНЕРАЦИЯ КАБИНЕТОВ (rooms.csv) ===
rooms_data = []
header_rooms = ["Name", "Type", "Capacity", "Building"]

# Обычные классы: 2 корпуса, 4 этажа, по 15 кабинетов на этаж
for corp in CORPS:
    for floor in range(1, 5):
        for num in range(1, 16):
            # Пример: 101А, 215В
            name = f"{floor}{num:02d}{corp}"
            rooms_data.append([name, "standard", 30, corp])

# Спец. кабинеты в каждом корпусе
for corp in CORPS:
    rooms_data.append([f"Хімія 1{corp}", "chemistry", 30, corp])
    rooms_data.append([f"Хімія 2{corp}", "chemistry", 30, corp])
    rooms_data.append([f"Фізика 1{corp}", "physics", 30, corp])
    rooms_data.append([f"Фізика 2{corp}", "physics", 30, corp])
    rooms_data.append([f"Біологія 1{corp}", "bio", 30, corp])
    # IT классы
    for i in range(1, 6):
        rooms_data.append([f"IT-{i}{corp}", "it", 15, corp])

# Спортзалы (Отдельное здание "Sport")
# 4 зала, каждый делим на 3 сектора = 12 мест
for i in range(1, 5):
    rooms_data.append([f"Спортзал {i} (Сектор А)", "gym", 30, "Sport"])
    rooms_data.append([f"Спортзал {i} (Сектор Б)", "gym", 30, "Sport"])
    rooms_data.append([f"Спортзал {i} (Сектор В)", "gym", 30, "Sport"])

with open("rooms.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(header_rooms)
    writer.writerows(rooms_data)
print(f"✅ rooms.csv создан: {len(rooms_data)} помещений.")

# === 2. ГЕНЕРАЦИЯ НАГРУЗКИ (workload.csv) ===
workload_data = []
header_workload = ["Teacher", "Subject", "Class", "Hours", "Shift", "Subgroup", "RoomType"]

SUBJECTS = [
    "Математика", "Алгебра", "Геометрія", "Інформатика", "Фізика", "Хімія",
    "Біологія", "Географія", "Історія України", "Англ. мова", "Укр. мова",
    "Укр. літ.", "Фізична культура", "Захист України", "Мистецтво", "Технології"
]

# Создаем учителей
teachers = []
for i in range(1, TEACHERS_COUNT + 1):
    subj = random.choice(SUBJECTS)
    teachers.append({"name": f"Учитель_{subj}_{i}", "subject": subj, "hours": 0})

# Группируем учителей по предметам
teachers_by_subj = {s: [] for s in SUBJECTS}
for t in teachers:
    teachers_by_subj[t["subject"]].append(t)

# Создаем классы
classes = []
letters = "АБВГДЕЖЗИК"
count = 0
for grade in range(1, 12):
    for char in letters:
        if count >= CLASSES_COUNT: break
        # 1-5 и 10-11 классы - 1 смена, 6-9 - 2 смена
        shift = 2 if 6 <= grade <= 9 else 1
        classes.append({"name": f"{grade}-{char}", "shift": shift, "grade": grade})
        count += 1

# Раздаем уроки
for cls in classes:
    grade = cls["grade"]

    # План (упрощенный)
    plan = {"Укр. мова": 3, "Математика": 4, "Англ. мова": 3, "Фізична культура": 3, "Інформатика": 2}
    if grade >= 7:
        plan.update({"Фізика": 2, "Хімія": 2, "Біологія": 2, "Географія": 2, "Історія України": 2})

    for subj, hours in plan.items():
        # Тип кабинета
        rtype = "standard"
        if "Фізична" in subj:
            rtype = "gym"
        elif "Інформатика" in subj:
            rtype = "it"
        elif "Хімія" in subj:
            rtype = "chemistry"
        elif "Фізика" in subj:
            rtype = "physics"
        elif "Біологія" in subj:
            rtype = "bio"

        # Деление на группы
        is_split = subj in ["Англ. мова", "Інформатика"]


        def get_teacher(s):
            pool = teachers_by_subj.get(s, [])
            if not pool: return "Teacher_Auto"
            pool.sort(key=lambda x: x["hours"])  # Берем наименее загруженного
            t = pool[0]
            t["hours"] += hours
            return t["name"]


        if is_split:
            workload_data.append([get_teacher(subj), subj, cls["name"], hours, cls["shift"], "1", rtype])
            workload_data.append([get_teacher(subj), subj, cls["name"], hours, cls["shift"], "2", rtype])
        else:
            workload_data.append([get_teacher(subj), subj, cls["name"], hours, cls["shift"], "whole", rtype])

with open("workload.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(header_workload)
    writer.writerows(workload_data)
print(f"✅ workload.csv создан: {len(workload_data)} записей.")