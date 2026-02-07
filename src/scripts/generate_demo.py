import csv
import math
import random
import os
import sys

# Добавляем путь к корню проекта, чтобы импортировать ministry_norms
sys.path.append(os.getcwd())

try:
    from src.utils.ministry_norms import MINISTRY_REQUIREMENTS
except ImportError:
    print("⚠️ Ошибка: Не найден файл src/utils/ministry_norms.py")
    print("Убедитесь, что запускаете скрипт из корня проекта.")
    sys.exit(1)

# === НАСТРОЙКИ ГЕНЕРАЦИИ ===
OUTPUT_FOLDER = "uploads"  # Куда сохранять CSV
CLASSES_LETTERS = "АБВ"  # 3 класса в параллели (можно добавить "ГД")
TEACHER_RATE = 23  # Целевая ставка (чем выше, тем меньше окон)
MAX_TEACHER_LOAD = 28  # Абсолютный максимум часов для человека

# Смены: 6-9 классы во вторую смену, остальные в первую
SHIFT_MAPPING = {
    1: 1, 2: 1, 3: 1, 4: 1, 5: 1,
    6: 2, 7: 2, 8: 2, 9: 2,
    10: 1, 11: 1
}


def generate_full_school():
    # Создаем папку, если нет
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    print(f"🚀 Начало генерации демо-данных в папку '{OUTPUT_FOLDER}/'...")

    # ==========================================
    # 1. ГЕНЕРАЦИЯ ИНФРАСТРУКТУРЫ (ROOMS)
    # ==========================================
    rooms_rows = []
    header_rooms = ["Name", "Type", "Capacity", "Building"]

    # --- Корпуса А и В ---
    for corp in ['А', 'В']:
        # 4 этажа, по 15 кабинетов (101А...415А)
        for floor in range(1, 5):
            for num in range(1, 16):
                rooms_rows.append([f"{floor}{num:02d}{corp}", "standard", 30, corp])

        # Спец. кабинеты (по 2 на корпус для надежности)
        for i in range(1, 3):
            rooms_rows.append([f"Хімія-{i}{corp}", "chemistry", 30, corp])
            rooms_rows.append([f"Фізика-{i}{corp}", "physics", 30, corp])
            rooms_rows.append([f"Біологія-{i}{corp}", "bio", 30, corp])

        # IT классы (нужно много, так как группы делятся)
        for i in range(1, 5):
            rooms_rows.append([f"IT-{i}{corp}", "it", 16, corp])

    # --- Спортзал (Отдельное здание) ---
    # Делим залы на сектора, чтобы проводить 3 урока одновременно в одном большом зале
    for gym_num in range(1, 5):  # 4 больших зала
        for sector in ["А", "Б", "В"]:  # 3 сектора в каждом
            rooms_rows.append([f"Спортзал {gym_num}-{sector}", "gym", 30, "Sport"])

    # Сохраняем rooms.csv
    rooms_path = os.path.join(OUTPUT_FOLDER, "rooms.csv")
    with open(rooms_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header_rooms)
        writer.writerows(rooms_rows)
    print(f"✅ Инфраструктура: {len(rooms_rows)} помещений (включая сектора залов).")

    # ==========================================
    # 2. РАСЧЕТ СПРОСА (DEMAND)
    # ==========================================
    # Собираем все уроки, которые нужно провести
    tasks = []
    total_subject_demand = {}  # {"Математика": 150 часов, ...}

    print("📊 Расчет нагрузки по нормам МОН...")

    for grade in range(1, 12):
        norms = MINISTRY_REQUIREMENTS.get(grade, {})
        shift = SHIFT_MAPPING.get(grade, 1)

        for letter in CLASSES_LETTERS:
            class_name = f"{grade}-{letter}"

            for subj, hours_raw in norms.items():
                hours = float(hours_raw)
                if hours <= 0: continue

                # Деление на подгруппы
                is_split = False
                if subj in ["Англ. мова", "Нім. мова", "Інформатика", "Захист України"] and grade > 4:
                    is_split = True

                # Если деление, часов нужно в 2 раза больше (на каждую группу)
                total_hours = hours * (2 if is_split else 1)

                # Округляем вверх (1.5 -> 2) для сетки
                sched_hours = int(math.ceil(hours))

                total_subject_demand[subj] = total_subject_demand.get(subj, 0) + total_hours

                tasks.append({
                    "class": class_name,
                    "subj": subj,
                    "hours": sched_hours,
                    "shift": shift,
                    "split": is_split
                })

    # ==========================================
    # 3. НАЙМ ПЕРСОНАЛА (TEACHERS)
    # ==========================================
    # Нанимаем ровно столько, сколько нужно, с высокой загрузкой
    teachers_db = {}  # { "Математика": [ {name, limit, current}, ... ] }

    print(f"👥 Формирование штата (Целевая ставка: {TEACHER_RATE} ч/нед)...")

    for subj, needed_hours in total_subject_demand.items():
        # Сколько учителей нужно?
        count = math.ceil(needed_hours / TEACHER_RATE)
        if count < 1: count = 1  # Хотя бы один нужен

        staff = []
        for i in range(1, count + 1):
            # Рандомим лимит, но держим его высоким
            limit = random.choice([22, 24, 25, 26, MAX_TEACHER_LOAD])
            t_name = f"{subj}_Teach_{i}"
            staff.append({"name": t_name, "limit": limit, "current": 0})

        teachers_db[subj] = staff

    # ==========================================
    # 4. РАСПРЕДЕЛЕНИЕ НАГРУЗКИ (WORKLOAD)
    # ==========================================
    workload_rows = []
    header_workload = ["Teacher", "Subject", "Class", "Hours", "MaxHours", "Shift", "Subgroup", "RoomType"]

    vacancies_count = 0

    for task in tasks:
        subj = task["subj"]
        hrs = task["hours"]

        # Определяем тип комнаты
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

        # Функция поиска учителя (Стратегия: УПЛОТНЕНИЕ)
        def assign_teacher():
            nonlocal vacancies_count
            pool = teachers_db.get(subj, [])

            # Фильтруем тех, у кого есть место
            candidates = [t for t in pool if t["current"] + hrs <= t["limit"]]

            if not candidates:
                # Если никто не влезает -> Вакансия
                vacancies_count += 1
                return "Вакансия (" + subj + ")", ""

                # СОРТИРОВКА: Берем самого ЗАГРУЖЕННОГО (reverse=True).
            # Зачем? Чтобы "добить" ему часы до ставки и не оставлять "хвостов".
            # Это уменьшает количество "дыр" в расписании.
            candidates.sort(key=lambda x: x["current"], reverse=True)

            chosen = candidates[0]
            chosen["current"] += hrs
            return chosen["name"], chosen["limit"]

        if task["split"]:
            # Группа 1
            t1, l1 = assign_teacher()
            workload_rows.append([t1, subj, task["class"], hrs, l1, task["shift"], "1", rtype])
            # Группа 2
            t2, l2 = assign_teacher()
            workload_rows.append([t2, subj, task["class"], hrs, l2, task["shift"], "2", rtype])
        else:
            t, l = assign_teacher()
            workload_rows.append([t, subj, task["class"], hrs, l, task["shift"], "whole", rtype])

    # Сохраняем workload.csv
    workload_path = os.path.join(OUTPUT_FOLDER, "workload.csv")
    with open(workload_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header_workload)
        writer.writerows(workload_rows)

    print(f"✅ Нагрузка: {len(workload_rows)} записей.")
    print(f"⚠️ Вакансий создано: {vacancies_count} (там, где не хватило учителей).")
    print(f"📂 Файлы сохранены в папку: {os.path.abspath(OUTPUT_FOLDER)}")


if __name__ == "__main__":
    generate_full_school()
