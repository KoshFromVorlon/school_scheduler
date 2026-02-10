from ortools.sat.python import cp_model
from src.extensions import db
from src.models.schedule import ScheduleEntry
from src.models.enums import RoomType, SubgroupType
from src.utils.constraints_config import GLOBAL_CONSTRAINTS, ConstraintType
import time


class SchoolScheduler:
    def __init__(self, school_id):
        self.school_id = school_id
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # === НАСТРОЙКИ "ТЯЖЕЛОГО" РАСЧЕТА ===
        # Увеличили до 600 секунд для поиска почти идеального варианта
        self.solver.parameters.max_time_in_seconds = 600.0
        self.solver.parameters.num_search_workers = 8
        self.solver.parameters.random_seed = 42
        self.solver.parameters.log_search_progress = True

        self.time_vars = {}

    def run_algorithm(self, workloads, slots, rooms):
        print(f"🧠 ЗАПУСК УНИВЕРСАЛЬНОГО SOLVER: {len(workloads)} нагрузок.")
        start_time = time.time()

        # Сортировка для стабильности результата
        workloads.sort(key=lambda x: x.id)
        slots.sort(key=lambda x: (x.day_of_week, x.period_number))

        # Кэш инфраструктуры
        room_capacities = {rt: 0 for rt in RoomType}
        for r in rooms:
            room_capacities[r.room_type] += 1

        workloads_by_type = {}
        for w in workloads:
            workloads_by_type.setdefault(w.required_room_type, []).append(w)

        # 1. СОЗДАНИЕ ПЕРЕМЕННЫХ РЕШЕНИЯ
        for w in workloads:
            for s in slots:
                # Жесткие границы смен
                if w.group.shift == 1 and s.period_number > 8: continue
                if w.group.shift == 2 and s.period_number < 5: continue

                self.time_vars[(w.id, s.id)] = self.model.NewBoolVar(
                    f'w{w.id}_d{s.day_of_week}_p{s.period_number}'
                )

        # 2. ПРИМЕНЕНИЕ ВНЕШНИХ ОГРАНИЧЕНИЙ (ИЗ ФАЙЛА КОНФИГУРАЦИИ)
        objectives = []
        self._apply_external_constraints(workloads, slots, objectives)

        # 3. ПОСТРОЕНИЕ ПЛАНА И ЦЕЛЕЙ (МАГНИТЫ И ГРАВИТАЦИЯ)
        teacher_schedule = {}  # teacher_id -> day -> period -> [vars]

        for w in workloads:
            w_vars = []
            for s in slots:
                if (w.id, s.id) in self.time_vars:
                    var = self.time_vars[(w.id, s.id)]
                    w_vars.append(var)

                    # Гравитация (прижимаем к началу смены)
                    # Чем дальше от старта смены, тем больше штраф
                    dist = s.period_number if w.group.shift == 1 else abs(s.period_number - 6)
                    objectives.append(var * -(dist ** 2))

                    if not w.teacher.is_vacancy:
                        t_day = teacher_schedule.setdefault(w.teacher_id, {}).setdefault(s.day_of_week, {})
                        t_day.setdefault(s.period_number, []).append(var)

            # Hard Constraint: Нагрузка должна быть выполнена полностью
            if w_vars:
                self.model.Add(sum(w_vars) == w.hours_per_week)

        # "Магнит" окон: Даем огромный бонус за уроки, идущие подряд
        for t_id, days in teacher_schedule.items():
            for day, p_map in days.items():
                busy_at_period = {}
                for p in range(1, 14):
                    b_var = self.model.NewBoolVar(f'busy_t{t_id}_d{day}_p{p}')
                    if p in p_map:
                        self.model.Add(sum(p_map[p]) == b_var)
                    else:
                        self.model.Add(b_var == 0)
                    busy_at_period[p] = b_var

                for p in range(1, 13):
                    is_consecutive = self.model.NewBoolVar(f'cons_t{t_id}_d{day}_p{p}')
                    # Если занят в p и p+1 одновременно -> бонус
                    self.model.AddBoolAnd([busy_at_period[p], busy_at_period[p + 1]]).OnlyEnforceIf(is_consecutive)
                    objectives.append(is_consecutive * 5000)

        # Главная цель — максимизация суммы всех бонусов и минимизация штрафов
        self.model.Maximize(sum(objectives))

        # 4. СТАНДАРТНЫЕ ЖЕСТКИЕ ПРАВИЛА (КОНФЛИКТЫ)
        self._add_standard_constraints(teacher_schedule, workloads, slots, room_capacities, workloads_by_type)

        # 5. ЗАПУСК ОПТИМИЗАТОРА
        print(f"⏳ Решение запущено (лимит {self.solver.parameters.max_time_in_seconds} сек)...")
        status = self.solver.Solve(self.model)

        duration = time.time() - start_time
        print(f"⏱ Время расчета: {duration:.2f} сек. Статус: {self.solver.StatusName(status)}")

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(f"✅ Оценка качества (Objective): {self.solver.ObjectiveValue()}")
            self._assign_rooms_greedy(workloads, slots, rooms)
            return True

        print("💥 Не удалось найти решение, удовлетворяющее всем ЖЕСТКИМ правилам.")
        return False

    def _apply_external_constraints(self, workloads, slots, objectives):
        """Метод для обработки правил из constraints_config.py"""
        group_ids = list(set(w.group_id for w in workloads))

        for rule in GLOBAL_CONSTRAINTS:
            # ПРАВИЛО: Запрет на N уроков подряд (например, 3 физики)
            if rule["type"] == ConstraintType.MAX_CONTINUOUS:
                for gid in group_ids:
                    for subj_name in rule["subjects"]:
                        for day in range(1, 6):
                            day_slots = [s for s in slots if s.day_of_week == day]
                            limit = rule["max_value"]
                            for i in range(len(day_slots) - limit):
                                window = day_slots[i: i + limit + 1]
                                window_vars = [self.time_vars[(w.id, s.id)] for s in window
                                               for w in workloads if w.group_id == gid
                                               and w.subject.name == subj_name
                                               and (w.id, s.id) in self.time_vars]
                                if window_vars:
                                    self.model.Add(sum(window_vars) <= limit)

            # ПРАВИЛО: Лимит одного предмета в день для класса
            elif rule["type"] == ConstraintType.MAX_PER_DAY:
                for gid in group_ids:
                    for subj_name in rule["subjects"]:
                        for day in range(1, 6):
                            daily_vars = [self.time_vars[(w.id, s.id)] for s in slots
                                          for w in workloads if s.day_of_week == day
                                          and w.group_id == gid and w.subject.name == subj_name
                                          and (w.id, s.id) in self.time_vars]
                            if daily_vars:
                                self.model.Add(sum(daily_vars) <= rule["max_value"])

            # ПРАВИЛО: Приоритетные часы (Soft constraint)
            elif rule["type"] == ConstraintType.PERIOD_PRIORITY:
                for w in workloads:
                    if w.subject.name in rule["subjects"]:
                        for s in slots:
                            if (w.id, s.id) in self.time_vars and s.period_number in rule["preferred_periods"]:
                                objectives.append(self.time_vars[(w.id, s.id)] * rule["bonus"])

    def _add_standard_constraints(self, teacher_schedule, workloads, slots, room_capacities, workloads_by_type):
        # Учитель не может быть в двух местах
        for t_days in teacher_schedule.values():
            for p_map in t_days.values():
                for v_list in p_map.values():
                    self.model.Add(sum(v_list) <= 1)

        # Класс не может быть на двух уроках (с учетом подгрупп)
        group_vars = {}
        for (wid, sid), var in self.time_vars.items():
            w = next(x for x in workloads if x.id == wid)
            group_vars.setdefault((w.group_id, sid), []).append((w.subgroup, var))

        for (gid, sid), entries in group_vars.items():
            whole_lesson = sum([v for sub, v in entries if sub == SubgroupType.WHOLE_CLASS])
            self.model.Add(whole_lesson <= 1)
            for sub, v in entries:
                if sub != SubgroupType.WHOLE_CLASS:
                    self.model.Add(whole_lesson + v <= 1)

        # Кабинеты (не превышать вместимость)
        for s in slots:
            for rt, w_list in workloads_by_type.items():
                vars_in = [self.time_vars[(w.id, s.id)] for w in w_list if (w.id, s.id) in self.time_vars]
                if vars_in:
                    limit = room_capacities.get(rt, room_capacities.get(RoomType.STANDARD, 0))
                    if rt == RoomType.GYM and room_capacities.get(RoomType.GYM, 0) == 0:
                        self.model.Add(sum(vars_in) == 0)
                    else:
                        self.model.Add(sum(vars_in) <= limit)

    def _assign_rooms_greedy(self, workloads, slots, rooms):
        """Распределение кабинетов после того, как сетка времени утверждена."""
        final_schedule = []
        active = [(wid, sid) for (wid, sid), var in self.time_vars.items() if self.solver.Value(var)]

        from collections import defaultdict
        s_map = defaultdict(list)
        for wid, sid in active: s_map[sid].append(wid)

        w_map = {w.id: w for w in workloads}
        r_map = {r.id: r for r in rooms}

        for sid, w_ids in s_map.items():
            avail = list(r_map.values())
            # Сначала даем кабинеты спец. предметам
            curr_w = sorted([w_map[wid] for wid in w_ids],
                            key=lambda x: 0 if x.required_room_type != RoomType.STANDARD else 1)

            for w in curr_w:
                cands = [r for r in avail if r.room_type == w.required_room_type]
                if not cands and w.required_room_type != RoomType.GYM:
                    cands = [r for r in avail if r.room_type == RoomType.STANDARD]

                if cands:
                    chosen = cands[0]
                    avail.remove(chosen)
                    final_schedule.append(ScheduleEntry(
                        workload_id=w.id, timeslot_id=sid, room_id=chosen.id
                    ))

        db.session.query(ScheduleEntry).delete()
        db.session.add_all(final_schedule)
        db.session.commit()