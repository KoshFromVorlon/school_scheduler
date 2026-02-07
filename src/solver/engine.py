from ortools.sat.python import cp_model
from src.extensions import db
from src.models.schedule import ScheduleEntry
from src.models.enums import RoomType, SubgroupType
import math


class SchoolScheduler:
    def __init__(self, school_id):
        self.school_id = school_id
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        # Дадим ему подумать чуть дольше, чтобы склеить окна
        self.solver.parameters.max_time_in_seconds = 120.0
        self.solver.parameters.num_search_workers = 8
        self.time_vars = {}

    def run_algorithm(self, workloads, slots, rooms):
        print(f"🚀 УМНОЕ РАСПИСАНИЕ: {len(workloads)} нагрузок.")

        workloads.sort(key=lambda x: x.id)
        slots.sort(key=lambda x: (x.day_of_week, x.period_number))

        room_capacities = {}
        for r in rooms: room_capacities[r.room_type] = room_capacities.get(r.room_type, 0) + 1
        workloads_by_type = {}
        for w in workloads: workloads_by_type.setdefault(w.required_room_type, []).append(w)

        # 1. ПЕРЕМЕННЫЕ
        for w in workloads:
            for s in slots:
                if w.group.shift == 1 and s.period_number > 8: continue
                if w.group.shift == 2 and s.period_number < 5: continue
                self.time_vars[(w.id, s.id)] = self.model.NewBoolVar(f'w{w.id}_s{s.id}')

        objectives = []

        # Группируем нагрузку по учителям
        teacher_vars = {}  # teacher_id -> day -> list_of_vars_sorted_by_period

        for w in workloads:
            w_vars = []
            for s in slots:
                if (w.id, s.id) in self.time_vars:
                    var = self.time_vars[(w.id, s.id)]
                    w_vars.append(var)

                    # 1. Штраф за поздние уроки (прижимаем к утру)
                    penalty = (s.period_number ** 2)
                    if w.group.shift == 2: penalty = ((s.period_number - 4) ** 2)
                    objectives.append(var * (-penalty))

                    # Собираем переменные учителя для анализа
                    if not w.teacher.is_vacancy:
                        t_day_map = teacher_vars.setdefault(w.teacher_id, {})
                        t_day_list = t_day_map.setdefault(s.day_of_week, [])
                        # Сохраняем (номер_урока, переменная)
                        t_day_list.append((s.period_number, var))

            if w_vars:
                self.model.Add(sum(w_vars) == w.hours_per_week)
            else:
                print(f"⚠️ Ошибка слотов: {w.subject} {w.group.name}")

        # === 2. ЭФФЕКТ МАГНИТА (УБИРАЕМ ОКНА) ===
        # Для каждого учителя и каждого дня
        for t_id, days_map in teacher_vars.items():
            for day, lesson_tuples in days_map.items():
                # Сортируем по номеру урока: 1, 2, 3...
                lesson_tuples.sort(key=lambda x: x[0])

                # Группируем переменные по номеру урока
                vars_by_period = {}
                for p_num, var in lesson_tuples:
                    vars_by_period.setdefault(p_num, []).append(var)

                # Создаем вспомогательные переменные "Учитель занят на уроке N"
                busy_vars = {}
                for p_num in range(1, 14):
                    if p_num in vars_by_period:
                        b_var = self.model.NewBoolVar(f'busy_t{t_id}_d{day}_p{p_num}')
                        self.model.Add(sum(vars_by_period[p_num]) >= 1).OnlyEnforceIf(b_var)
                        self.model.Add(sum(vars_by_period[p_num]) == 0).OnlyEnforceIf(b_var.Not())
                        busy_vars[p_num] = b_var
                    else:
                        # Если уроков нет вообще в этот слот - ставим просто 0 (число)
                        busy_vars[p_num] = 0

                # МАГНИТ:
                # Если занят в P и занят в P+1 -> Бонус +5000
                for p in range(1, 13):
                    cur = busy_vars[p]
                    nxt = busy_vars[p + 1]

                    # ИСПРАВЛЕНИЕ: Проверяем, что это не число 0, а переменная
                    # (is not 0 - работает для проверки, что это объект переменной)
                    if cur is not 0 and nxt is not 0:
                        # Создаем переменную "consecutive" (последовательные)
                        is_consecutive = self.model.NewBoolVar(f'cons_t{t_id}_d{day}_p{p}')

                        # Логика: is_consecutive ИСТИНА, только если cur=1 И nxt=1
                        self.model.AddBoolAnd([cur, nxt]).OnlyEnforceIf(is_consecutive)

                        # Добавляем ОГРОМНЫЙ бонус в цель
                        objectives.append(is_consecutive * 5000)

        self.model.Maximize(sum(objectives))

        # 3. ЖЕСТКИЕ ОГРАНИЧЕНИЯ (Конфликты)
        # Учитель
        for t_id, days_map in teacher_vars.items():
            for day, lesson_tuples in days_map.items():
                vars_by_period = {}
                for p_num, var in lesson_tuples:
                    vars_by_period.setdefault(p_num, []).append(var)
                for v_list in vars_by_period.values():
                    self.model.Add(sum(v_list) <= 1)

        # Класс
        group_conflicts = {}
        for (wid, sid), var in self.time_vars.items():
            w = next(x for x in workloads if x.id == wid)
            g_entry = group_conflicts.setdefault((w.group_id, sid), {'whole': [], 'subs': []})
            if w.subgroup == SubgroupType.WHOLE_CLASS:
                g_entry['whole'].append(var)
            else:
                g_entry['subs'].append(var)

        for data in group_conflicts.values():
            whole = sum(data['whole'])
            for sub_var in data['subs']: self.model.Add(whole + sub_var <= 1)
            self.model.Add(whole <= 1)

        # Кабинеты
        for s in slots:
            for r_type, w_list in workloads_by_type.items():
                cap = room_capacities.get(r_type, 0)
                if cap == 0 and r_type != RoomType.GYM: cap = room_capacities.get(RoomType.STANDARD, 0)
                vars_in = [self.time_vars[(w.id, s.id)] for w in w_list if (w.id, s.id) in self.time_vars]
                if vars_in: self.model.Add(sum(vars_in) <= cap)

        # === РЕШЕНИЕ ===
        print("⏳ Ищем лучшее расписание (склеиваем окна)...")
        status = self.solver.Solve(self.model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("✅ Найдено! Расставляем кабинеты...")
            self._assign_rooms(workloads, slots, rooms)
            return True
        else:
            print("💥 Не вышло.")
            return False

    def _assign_rooms(self, workloads, slots, rooms):
        final_schedule = []
        schedule_map = {s.id: [] for s in slots}
        for (wid, sid), var in self.time_vars.items():
            if self.solver.Value(var): schedule_map[sid].append(wid)

        w_obj_map = {w.id: w for w in workloads}

        for s in slots:
            active_ids = schedule_map[s.id]
            if not active_ids: continue
            available_rooms = {r.id: r for r in rooms}
            active_w = [w_obj_map[wid] for wid in active_ids]
            active_w.sort(key=lambda x: 0 if x.required_room_type != RoomType.STANDARD else 1)

            for w in active_w:
                req = w.required_room_type
                cands = [r for r in available_rooms.values() if r.room_type == req]
                if not cands and req != RoomType.GYM: cands = [r for r in available_rooms.values() if
                                                               r.room_type == RoomType.STANDARD]

                if cands:
                    chosen = cands[0]
                    del available_rooms[chosen.id]
                    final_schedule.append(ScheduleEntry(workload_id=w.id, timeslot_id=s.id, room_id=chosen.id))

        db.session.query(ScheduleEntry).delete()
        db.session.add_all(final_schedule)
        db.session.commit()