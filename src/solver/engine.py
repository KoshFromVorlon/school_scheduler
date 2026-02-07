from ortools.sat.python import cp_model
from src.extensions import db
from src.models.schedule import ScheduleEntry
from src.models.enums import RoomType, SubgroupType


class SchoolScheduler:
    def __init__(self, school_id):
        self.school_id = school_id
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Настройки: быстрый поиск
        self.solver.parameters.max_time_in_seconds = 60.0
        self.solver.parameters.num_search_workers = 8
        self.solver.parameters.log_search_progress = True

        # Переменные Фазы 1: (workload_id, slot_id) -> BoolVar
        self.time_vars = {}

    def run_algorithm(self, workloads, slots, rooms):
        print(f"🚀 ЗАПУСК ТУРБО-СОЛВЕРА: {len(workloads)} нагрузок, {len(slots)} слотов.")

        # === ПОДГОТОВКА ДАННЫХ ===
        workloads.sort(key=lambda x: x.id)
        slots.sort(key=lambda x: (x.day_of_week, x.period_number))

        # Считаем вместимость по типам комнат
        # {RoomType.STANDARD: 85, RoomType.GYM: 12 ...}
        room_capacities = {}
        rooms_by_type = {}
        for r in rooms:
            room_capacities[r.room_type] = room_capacities.get(r.room_type, 0) + 1
            rooms_by_type.setdefault(r.room_type, []).append(r)

        # ==========================================
        # ФАЗА 1: ОПРЕДЕЛЕНИЕ ВРЕМЕНИ (Time Assignment)
        # ==========================================

        # 1. Переменные: "Урок W проходит в Слот S"
        # Мы НЕ выбираем комнату здесь, только проверяем их количество

        workloads_by_type = {}  # type -> [w1, w2...]

        for w in workloads:
            workloads_by_type.setdefault(w.required_room_type, []).append(w)

            for s in slots:
                # Фильтр смен (Жесткая оптимизация)
                if w.group.shift == 1 and s.period_number > 8: continue
                if w.group.shift == 2 and s.period_number < 5: continue

                # Создаем переменную
                var = self.model.NewBoolVar(f'w{w.id}_s{s.id}')
                self.time_vars[(w.id, s.id)] = var

        print(f"📊 Фаза 1: {len(self.time_vars)} переменных (вместо миллионов).")

        # 2. Ограничения Фазы 1

        # А. Конфликты Учителей (если не вакансия)
        teacher_map = {}
        # Б. Конфликты Групп
        group_map = {}

        for (wid, sid), var in self.time_vars.items():
            w = next(x for x in workloads if x.id == wid)

            # Учителя
            if not w.teacher.is_vacancy:
                teacher_map.setdefault((w.teacher_id, sid), []).append(var)

            # Группы (класс)
            g_entry = group_map.setdefault((w.group_id, sid), {'whole': [], 'subs': []})
            if w.subgroup == SubgroupType.WHOLE_CLASS:
                g_entry['whole'].append(var)
            else:
                g_entry['subs'].append(var)

        # Применяем ограничения учителей
        for vars_list in teacher_map.values():
            self.model.Add(sum(vars_list) <= 1)

        # Применяем ограничения групп
        for (gid, sid), data in group_map.items():
            whole = sum(data['whole'])
            # Если урок у всего класса, подгруппы не могут.
            # Если подгруппа занята, весь класс не может.
            for sub_var in data['subs']:
                self.model.Add(whole + sub_var <= 1)
            # Весь класс сам с собой
            self.model.Add(whole <= 1)
            # Подгруппы между собой НЕ конфликтуют (Group 1 и Group 2 могут быть одновременно)

        # В. Вместимость комнат (Capacity Check)
        # Для каждого слота и каждого типа комнаты:
        # Сумма уроков этого типа <= Количество комнат этого типа
        for s in slots:
            for r_type, w_list in workloads_by_type.items():
                capacity = room_capacities.get(r_type, 0)

                # Если спец. комнат нет, ищем в стандартных (fallback)
                if capacity == 0 and r_type != RoomType.STANDARD:
                    # Если это не физра, разрешаем обычные классы
                    if r_type != RoomType.GYM:
                        capacity = room_capacities.get(RoomType.STANDARD, 0)

                vars_in_slot_for_type = []
                for w in w_list:
                    if (w.id, s.id) in self.time_vars:
                        vars_in_slot_for_type.append(self.time_vars[(w.id, s.id)])

                if vars_in_slot_for_type:
                    self.model.Add(sum(vars_in_slot_for_type) <= capacity)

        # Г. Цель: Максимизировать количество уроков (Best Effort)
        objective_vars = []
        for w in workloads:
            w_vars = [self.time_vars[(w.id, s.id)] for s in slots if (w.id, s.id) in self.time_vars]
            assigned_sum = sum(w_vars)
            self.model.Add(assigned_sum <= w.hours_per_week)
            objective_vars.append(assigned_sum)

        self.model.Maximize(sum(objective_vars))

        # 3. Решение Фазы 1
        print("⏳ Решаем Фазу 1 (Время)...")
        status = self.solver.Solve(self.model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("💥 Не удалось распределить время.")
            return False

        print(f"✅ Время распределено! ({self.solver.WallTime():.2f}c). Начинаем рассадку по кабинетам...")

        # ==========================================
        # ФАЗА 2: РАСПРЕДЕЛЕНИЕ ПО КАБИНЕТАМ (Room Assignment)
        # ==========================================
        # Это простой жадный алгоритм. Солвер тут не нужен, просто перебор.

        final_schedule = []

        # Группируем результаты Фазы 1 по слотам
        # slot_id -> [workload_id, workload_id...]
        schedule_map = {s.id: [] for s in slots}

        for (wid, sid), var in self.time_vars.items():
            if self.solver.Value(var):
                schedule_map[sid].append(wid)

        w_obj_map = {w.id: w for w in workloads}

        # Для каждого слота раздаем комнаты
        for s in slots:
            active_workloads_ids = schedule_map[s.id]
            if not active_workloads_ids: continue

            # Свободные комнаты в этом слоте (копия списка)
            available_rooms = {r.id: r for r in rooms}

            # Сортируем нагрузки: Сначала спец. кабинеты, потом обычные
            # Чтобы химию не заняли математикой
            active_workloads = [w_obj_map[wid] for wid in active_workloads_ids]
            active_workloads.sort(key=lambda x: 0 if x.required_room_type != RoomType.STANDARD else 1)

            for w in active_workloads:
                # Ищем подходящую комнату
                req_type = w.required_room_type

                # 1. Строгий поиск (по типу)
                candidates = [r for r in available_rooms.values() if r.room_type == req_type]

                # 2. Fallback (если не физра, можно в обычный)
                if not candidates and req_type != RoomType.GYM:
                    candidates = [r for r in available_rooms.values() if r.room_type == RoomType.STANDARD]

                if candidates:
                    # Берем первую попавшуюся (можно улучшить: искать тот же корпус)
                    # Пока берем просто первую
                    chosen_room = candidates[0]
                    del available_rooms[chosen_room.id]

                    final_schedule.append(ScheduleEntry(
                        workload_id=w.id,
                        timeslot_id=s.id,
                        room_id=chosen_room.id
                    ))
                else:
                    print(f"⚠️ Урок {w.subject} (ID {w.id}) потерян на Фазе 2: нет комнаты!")

        self._save_to_db(final_schedule)
        return True

    def _save_to_db(self, entries):
        db.session.query(ScheduleEntry).delete()
        db.session.add_all(entries)
        db.session.commit()
        print(f"💾 Записано {len(entries)} уроков в расписание.")