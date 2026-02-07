import csv
import random

# 1. ГЕНЕРАЦИЯ КАБИНЕТОВ (rooms.csv)
rooms_data = [["Name", "Type", "Capacity", "Building"]]
for corp in ['А', 'В']:
    for f in range(1, 5):
        for n in range(1, 14): rooms_data.append([f"{f}{n:02d}{corp}", "standard", 30, corp])
    rooms_data.append([f"Хімія {corp}", "chemistry", 30, corp])
    rooms_data.append([f"Фізика {corp}", "physics", 30, corp])
    rooms_data.append([f"Біологія {corp}", "bio", 30, corp])
    for i in range(1, 6): rooms_data.append([f"IT-{i}{corp}", "it", 15, corp])
for i in range(1, 5):
    for sec in ["А", "Б", "В"]: rooms_data.append([f"Спортзал {i}-{sec}", "gym", 30, "Sport"])

with open("rooms.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerows(rooms_data)
print("✅ rooms.csv создан.")

# 2. ГЕНЕРАЦИЯ НАГРУЗКИ С ВАКАНСИЯМИ (workload.csv)
header = ["Teacher", "Subject", "Class", "Hours", "MaxHours", "Shift", "Subgroup", "RoomType"]
rows = []

SUBJECTS = ["Математика", "Укр. мова", "Англ. мова", "Фізика", "Фізична культура"]

# Создаем штат с ДЕФИЦИТОМ и РАЗНЫМИ лимитами
teachers_db = {}
for subj in SUBJECTS:
    teachers_db[subj] = []
    # Всего 5 учителей на предмет (мало!)
    for i in range(1, 6):
        limit = random.choice([12, 18, 18, 25])  # Разные лимиты
        t_name = f"{subj}_Teach_{i}"
        teachers_db[subj].append({"name": t_name, "limit": limit, "current": 0})

classes = [f"{g}-{l}" for g in range(1, 12) for l in "АБВГД"]  # 55 классов

for cls in classes:
    grade = int(cls.split('-')[0])
    shift = 2 if 6 <= grade <= 9 else 1

    plan = {"Математика": 4, "Укр. мова": 3, "Англ. мова": 3, "Фізика": 2, "Фізична культура": 3}
    if grade < 7: plan.pop("Фізика", None)

    for subj, hours in plan.items():
        rtype = "standard"
        if "Фізична" in subj:
            rtype = "gym"
        elif "Фізика" in subj:
            rtype = "physics"

        # Пытаемся найти живого учителя
        pool = teachers_db.get(subj, [])
        pool.sort(key=lambda x: x["current"])  # Берем самого свободного

        assigned_name = "Auto"  # По умолчанию - Вакансия
        assigned_limit = ""

        for t in pool:
            if t["current"] + hours <= t["limit"]:
                t["current"] += hours
                assigned_name = t["name"]
                assigned_limit = t["limit"]
                break

        # Записываем
        is_split = subj == "Англ. мова"
        if is_split:
            rows.append([assigned_name, subj, cls, hours, assigned_limit, shift, "1", rtype])
            # Для второй группы
            assigned_name_2 = "Auto"
            assigned_limit_2 = ""
            for t in pool:  # Снова ищем в пуле
                if t["current"] + hours <= t["limit"]:
                    t["current"] += hours
                    assigned_name_2 = t["name"]
                    assigned_limit_2 = t["limit"]
                    break
            rows.append([assigned_name_2, subj, cls, hours, assigned_limit_2, shift, "2", rtype])
        else:
            rows.append([assigned_name, subj, cls, hours, assigned_limit, shift, "whole", rtype])

with open("workload.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print(f"✅ workload.csv создан ({len(rows)} строк). Излишки слиты в 'Auto'.")
