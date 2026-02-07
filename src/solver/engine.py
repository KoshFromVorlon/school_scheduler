from ortools.sat.python import cp_model
from src.extensions import db
from src.models.schedule import ScheduleEntry
from src.models.enums import RoomType, SubgroupType


class SchoolScheduler:
    def __init__(self, school_id):
        self.school_id = school_id
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Настройки: 2 минуты на поиск (достаточно для хорошего решения)
        self.solver.parameters.max_time_in_seconds = 120.0
        self.solver.parameters.num_search_workers = 8
        self.solver.parameters.log_search_progress = True

        self.grid = {}  # (workload_id, slot_id, room_id) -> BoolVar

    def run_algorithm(self, workloads, slots, rooms):
        print(f"🧩 Запуск солвера: {len(workloads)} нагрузок, {len(slots)} слотов, {len(rooms)} кабинетов.")

        # Сортировка
        workloads.sort(key=lambda x: x.id)
        rooms.sort(key=lambda x: x.id)
        slots.sort(key=lambda x: (x.day_of_week, x.period_number))

        # Оптимизация: Индекс кабинетов по типу
        rooms_by_type = {}
        for r in rooms:
            rooms_by_type.setdefault(r.room_type, []).append(r)

        # === 1. СОЗДАНИЕ ПЕРЕМЕННЫХ ===
        lesson_vars = {w.id: [] for w in workloads}

        total_needed = 0

        for w in workloads:
            needed_type = w.required_room_type
            available_rooms = rooms_by_type.get(needed_type, [])

            # Fallback на обычные кабинеты, если спец. нет (кроме физры)
            if not available_rooms and needed_type != RoomType.GYM:
                available_rooms = rooms_by_type.get(RoomType.STANDARD, [])

            for s in slots:
                # ОПТИМИЗАЦИЯ: Фильтр смен
                if w.group.shift == 1 and s.period_number > 8: continue  # 1 смена не учится вечером
                if w.group.shift == 2 and s.period_number < 5: continue  # 2 смена не учится утром

                for r in available_rooms:
                    var = self.model.NewBoolVar(f'w{w.id}_d{s.day_of_week}_p{s.period_number}_r{r.id}')
                    self.grid[(w.id, s.id, r.id)] = var
                    lesson_vars[w.id].append(var)

            total_needed += w.hours_per_week

        print(f"📊 Переменные созданы. Цель: {total_needed} уроков.")

        # === 2. ОГРАНИЧЕНИЯ ===

        # А. КОНФЛИКТЫ (Hard Constraints)
        teacher_to_vars = {}
        room_to_vars = {}
        group_to_vars = {}  # group_id -> slot_id -> list of vars

        for (wid, sid, rid), var in self.grid.items():
            w = next(x for x in workloads if x.id == wid)

            # Собираем переменные для учителя
            teacher_to_vars.setdefault((w.teacher_id, sid), []).append(var)

            # Для кабинета
            room_to_vars.setdefault((rid, sid), []).append(var)

            # Для класса (сложная логика подгрупп)
            g_map = group_to_vars.setdefault(w.group_id, {})
            s_list = g_map.setdefault(sid, [])
            s_list.append((w.subgroup, var))

        # 1. Учитель (только если это НЕ ВАКАНСИЯ)
        # Если учитель "Вакансия", он может вести хоть 100 уроков одновременно
        for (tid, sid), vars_list in teacher_to_vars.items():
            # Находим объект учителя (можно оптимизировать кэшем, но тут быстро)
            # В данном контексте workloads уже содержат teacher, но нам надо найти по ID
            # Проще проверить: все workloads с этим tid имеют одного учителя
            sample_w = next(x for x in workloads if x.teacher_id == tid)

            if not sample_w.teacher.is_vacancy:
                self.model.Add(sum(vars_list) <= 1)

        # 2. Кабинет (не резиновый)
        for vars_list in room_to_vars.values():
            self.model.Add(sum(vars_list) <= 1)

        # 3. Класс (Whole vs Subgroups)
        for gid, slots_map in group_to_vars.items():
            for sid, tuples in slots_map.items():
                whole_vars = [v for sub, v in tuples if sub == SubgroupType.WHOLE_CLASS]
                part_vars = [v for sub, v in tuples if sub != SubgroupType.WHOLE_CLASS]

                sum_whole = sum(whole_vars)

                # Если урок у всего класса, подгруппы не могут
                for pv in part_vars:
                    self.model.Add(sum_whole + pv <= 1)

                self.model.Add(sum_whole <= 1)
                # Группы 1 и 2 могут идти одновременно, это ОК.

        # Б. ЦЕЛЬ (Soft Constraints) - BEST EFFORT
        all_assigned = []
        for w in workloads:
            assigned = sum(lesson_vars[w.id])
            # Нельзя поставить больше часов, чем надо
            self.model.Add(assigned <= w.hours_per_week)
            all_assigned.append(assigned)

        # Максимизируем количество уроков
        self.model.Maximize(sum(all_assigned))

        # === 3. РЕШЕНИЕ ===
        print("⏳ Поиск решения...")
        status = self.solver.Solve(self.model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            placed = self.solver.ObjectiveValue()
            print(f"✅ УСПЕХ! Размещено {int(placed)} из {total_needed} уроков.")
            self._save_to_db(workloads, slots, rooms)
            return True
        else:
            print("💥 Не удалось найти решение (даже частичное).")
            return False

    def _save_to_db(self, workloads, slots, rooms):
        db.session.query(ScheduleEntry).delete()
        new_entries = []

        count = 0
        for (wid, sid, rid), var in self.grid.items():
            if self.solver.Value(var):
                new_entries.append(ScheduleEntry(workload_id=wid, timeslot_id=sid, room_id=rid))
                count += 1

        db.session.add_all(new_entries)
        db.session.commit()
        print(f"💾 Сохранено {count} записей.")