import csv
import math
import random
from src.utils.ministry_norms import MINISTRY_REQUIREMENTS

# === НАСТРОЙКИ (РЕАЛЬНАЯ ЖИЗНЬ) ===
CLASSES_LETTERS = "АБВ"
# СТАВКА ВЫШЕ: Чтобы не было окон, нагрузка должна быть плотной.
# Учитель с 24 часами имеет меньше шансов на окна, чем учитель с 12 часами.
TEACHER_RATE = 23
MAX_TEACHER_LOAD = 28  # Некоторые монстры берут и 30


def generate():
    print("🚀 Генерация: Плотная нагрузка (борьба с окнами)...")

    # 1. ИНФРАСТРУКТУРА (Без изменений)
    rooms_rows = []
    header_rooms = ["Name", "Type", "Capacity", "Building"]
    for corp in ['А', 'В']:
        for floor in range(1, 4):
            for num in range(1, 11):
                rooms_rows.append([f"{floor}{num:02d}{corp}", "standard", 30, corp])
        rooms_rows.append([f"Хімія-{corp}", "chemistry", 30, corp])
        rooms_rows.append([f"Фізика-{corp}", "physics", 30, corp])
        rooms_rows.append([f"Біологія-{corp}", "bio", 30, corp])
        rooms_rows.append([f"IT-1{corp}", "it", 15, corp])
        rooms_rows.append([f"IT-2{corp}", "it", 15, corp])
    for i in range(1, 5): rooms_rows.append([f"Спортзал {i}", "gym", 40, "Sport"])

    with open("rooms.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header_rooms)
        writer.writerows(rooms_rows)

    # 2. НАГРУЗКА
    workload_rows = []
    header_workload = ["Teacher", "Subject", "Class", "Hours", "MaxHours", "Shift", "Subgroup", "RoomType"]

    total_demand = {}
    tasks = []

    for grade in range(1, 12):
        norms = MINISTRY_REQUIREMENTS.get(grade, {})
        shift = 2 if 6 <= grade <= 8 else 1

        for letter in CLASSES_LETTERS:
            class_name = f"{grade}-{letter}"
            for subj, hours in norms.items():
                hours = float(hours)
                if hours <= 0: continue
                is_split = subj in ["Англ. мова", "Нім. мова", "Інформатика", "Захист України"] and grade > 4

                total_hours = hours * (2 if is_split else 1)
                total_demand[subj] = total_demand.get(subj, 0) + total_hours
                tasks.append({"class": class_name, "subj": subj, "hours": int(math.ceil(hours)), "shift": shift,
                              "split": is_split})

    # === ГЛАВНОЕ ИЗМЕНЕНИЕ: РАСЧЕТ ШТАТА ===
    teachers_db = {}

    for subj, needed_hours in total_demand.items():
        # Считаем штат по ПОВЫШЕННОЙ ставке (TEACHER_RATE = 23)
        # Это уменьшит кол-во учителей и уплотнит их графики.
        count = math.ceil(needed_hours / TEACHER_RATE)

        # Если предмета очень мало (например 6 часов на всю школу), берем 1 учителя
        if count < 1: count = 1

        staff = []
        for i in range(1, count + 1):
            # Разбрасываем нагрузку: кто-то 20, кто-то 28
            limit = random.choice([20, 22, 24, 26, 28])
            staff.append({"name": f"{subj}_Teach_{i}", "limit": limit, "current": 0})

        teachers_db[subj] = staff

    # РАСПРЕДЕЛЕНИЕ
    for task in tasks:
        subj = task["subj"]
        hrs = task["hours"]
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

        def get_teacher():
            pool = teachers_db.get(subj, [])
            # Ищем, кто влезет в лимит
            candidates = [t for t in pool if t["current"] + hrs <= t["limit"]]

            if not candidates:
                # Если все забиты под завязку (до 28 часов) - создаем вакансию
                return "Auto", ""

                # ВАЖНО: Сначала заполняем одного под завязку, потом второго.
            # (Раньше мы брали самого свободного -> размазывали нагрузку).
            # Теперь берем самого ЗАГРУЖЕННОГО, чтобы добить ему часы до плотности.
            candidates.sort(key=lambda x: x["current"], reverse=True)

            chosen = candidates[0]
            chosen["current"] += hrs
            return chosen["name"], chosen["limit"]

        if task["split"]:
            t1, l1 = get_teacher()
            workload_rows.append([t1, subj, task["class"], hrs, l1, task["shift"], "1", rtype])
            t2, l2 = get_teacher()
            workload_rows.append([t2, subj, task["class"], hrs, l2, task["shift"], "2", rtype])
        else:
            t, l = get_teacher()
            workload_rows.append([t, subj, task["class"], hrs, l, task["shift"], "whole", rtype])

    with open("workload.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header_workload)
        writer.writerows(workload_rows)

    print(f"✅ Успех: Нагрузка сгенерирована с учетом ставки ~{TEACHER_RATE} часов.")


if __name__ == "__main__":
    generate()