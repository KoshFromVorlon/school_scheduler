from ortools.sat.python import cp_model
from src.extensions import db
from src.models.schedule import ScheduleEntry
from src.models.enums import RoomType, SubgroupType
import time


class SchoolScheduler:
    def __init__(self, school_id):
        self.school_id = school_id
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # === НАСТРОЙКИ "ТЯЖЕЛОГО" РАСЧЕТА ===
        # 300 секунд = 5 минут. Для идеального результата можно ставить 600+.
        # Если решение найдено раньше, он остановится, если поймет, что лучше уже нельзя.
        self.solver.parameters.max_time_in_seconds = 600.0

        # Включаем все ядра процессора для параллельного поиска
        self.solver.parameters.num_search_workers = 8

        # Фиксируем seed для воспроизводимости результатов (чтобы баги можно было повторить)
        self.solver.parameters.random_seed = 42

        # Вывод логов процесса оптимизации в консоль
        self.solver.parameters.log_search_progress = True

        self.time_vars = {}

    def run_algorithm(self, workloads, slots, rooms):
        print(f"🧠 ЗАПУСК 'DEEP THOUGHT' SOLVER: {len(workloads)} нагрузок, {len(rooms)} комнат.")
        start_time = time.time()

        # Сортировка для детерминированности
        workloads.sort(key=lambda x: x.id)
        slots.sort(key=lambda x: (x.day_of_week, x.period_number))

        # Кэш вместимости комнат
        room_capacities = {}
        for r in rooms:
            room_capacities[r.room_type] = room_capacities.get(r.room_type, 0) + 1

        # Кэш нагрузок по типу комнат
        workloads_by_type = {}
        for w in workloads:
            workloads_by_type.setdefault(w.required_room_type, []).append(w)

        # ==========================================
        # 1. СОЗДАНИЕ ПЕРЕМЕННЫХ
        # ==========================================
        # var[(workload_id, slot_id)] = 1, если урок проходит в это время
        total_vars = 0
        for w in workloads:
            for s in slots:
                # Жесткие ограничения смен (Hard Constraints)
                # 1 смена: уроки 1-7 (или 1-8)
                if w.group.shift == 1 and s.period_number > 8: continue
                # 2 смена: уроки 6-13
                if w.group.shift == 2 and s.period_number < 5: continue

                var_name = f'w{w.id}_d{s.day_of_week}_p{s.period_number}'
                self.time_vars[(w.id, s.id)] = self.model.NewBoolVar(var_name)
                total_vars += 1

        print(f"📊 Создано {total_vars} переменных решения.")

        # ==========================================
        # 2. ЦЕЛИ ОПТИМИЗАЦИИ (OBJECTIVES)
        # ==========================================
        objectives = []

        # Вспомогательная структура: Учитель -> День -> {номер_урока: переменная}
        teacher_schedule = {}

        for w in workloads:
            w_vars = []
            for s in slots:
                if (w.id, s.id) in self.time_vars:
                    var = self.time_vars[(w.id, s.id)]
                    w_vars.append(var)

                    # --- ЦЕЛЬ А: ПРИЖИМАТЬ УРОКИ К НАЧАЛУ СМЕНЫ ---
                    # Чем позже урок, тем больше штраф.
                    # Это убирает "дыры" в конце дня.
                    penalty = s.period_number * s.period_number
                    if w.group.shift == 2:
                        # Для второй смены штрафуем за слишком ранние (до 5) или слишком поздние
                        penalty = (s.period_number - 4) * (s.period_number - 4)

                    objectives.append(var * (-penalty))  # Минус = штраф

                    # Собираем данные для учителя
                    if not w.teacher.is_vacancy:
                        t_day_map = teacher_schedule.setdefault(w.teacher_id, {})
                        t_slots = t_day_map.setdefault(s.day_of_week, {})
                        t_slots[s.period_number] = t_slots.get(s.period_number, []) + [var]

            # Hard Constraint: Урок должен состояться ровно столько раз, сколько положено
            if w_vars:
                self.model.Add(sum(w_vars) == w.hours_per_week)
            else:
                print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Нет доступных слотов для {w.subject} {w.group.name}")
                return False

        # --- ЦЕЛЬ Б: МАГНИТ (УБИРАЕМ ОКНА У УЧИТЕЛЕЙ) ---
        # "Если ведешь урок N, веди и урок N+1"
        print("🧲 Настройка магнитов расписания...")

        for t_id, days in teacher_schedule.items():
            for day, periods_map in days.items():
                # periods_map: { 1: [var_math_5a], 2: [var_math_6b], ... }

                # Создаем переменные "Учитель занят на уроке P" (IsBusy)
                # Это нужно, потому что у учителя может быть выбор из нескольких классов
                is_busy_vars = {}
                min_p = min(periods_map.keys())
                max_p = max(periods_map.keys())

                for p in range(min_p, max_p + 1):
                    if p in periods_map:
                        # Учитель занят, если хотя бы одна из переменных урока = 1
                        # sum(vars) <= 1 (так как он не может вести 2 урока), поэтому sum == is_busy
                        is_busy = self.model.NewBoolVar(f'busy_t{t_id}_d{day}_p{p}')
                        self.model.Add(sum(periods_map[p]) == is_busy)
                        is_busy_vars[p] = is_busy
                    else:
                        # В этот слот вообще нет уроков, которые он мог бы вести
                        is_busy_vars[p] = self.model.NewConstant(0)

                # Сама логика Магнита
                for p in range(min_p, max_p):
                    current = is_busy_vars[p]
                    next_one = is_busy_vars[p + 1]

                    # Переменная "Последовательность" = (current AND next_one)
                    consecutive = self.model.NewBoolVar(f'cons_t{t_id}_d{day}_p{p}')
                    self.model.AddBoolAnd([current, next_one]).OnlyEnforceIf(consecutive)
                    self.model.AddBoolOr([current.Not(), next_one.Not()]).OnlyEnforceIf(consecutive.Not())

                    # НАГРАДА: +1000 очков за отсутствие окна между уроками
                    objectives.append(consecutive * 1000)

        # Максимизируем "Счастье"
        self.model.Maximize(sum(objectives))

        # ==========================================
        # 3. ЖЕСТКИЕ ОГРАНИЧЕНИЯ (CONSTRAINTS)
        # ==========================================

        # A. Учитель не может вести 2 урока одновременно
        for t_id, days in teacher_schedule.items():
            for day, periods_map in days.items():
                for p, vars_list in periods_map.items():
                    if len(vars_list) > 1:
                        self.model.Add(sum(vars_list) <= 1)

        # B. Класс не может быть на 2 уроках одновременно
        # Группируем по (group_id, slot_id)
        group_vars = {}
        for (wid, sid), var in self.time_vars.items():
            w = next(x for x in workloads if x.id == wid)
            group_vars.setdefault((w.group_id, sid), []).append((w.subgroup, var))

        for (gid, sid), entries in group_vars.items():
            whole_vars = [v for sub, v in entries if sub == SubgroupType.WHOLE_CLASS]
            sub_vars = [v for sub, v in entries if sub != SubgroupType.WHOLE_CLASS]

            # Если есть урок для всего класса, подгруппы отдыхают
            if whole_vars:
                # Сумма всех уроков (и целых, и групп) <= 1?
                # Нет, группы могут идти параллельно.
                # Правило: (Whole == 1) => (Subs == 0)
                whole_sum = sum(whole_vars)
                self.model.Add(whole_sum <= 1)

                # Конфликт Whole vs Sub
                for sv in sub_vars:
                    self.model.Add(whole_sum + sv <= 1)

            # Подгруппы: Группа 1 не конфликтует с Группой 2, но Группа 1 не может быть в двух местах
            # Тут можно добавить логику проверки конфликтов внутри одной подгруппы,
            # но пока считаем, что workload корректен.

        # C. Вместимость кабинетов
        for s in slots:
            # Для каждого типа кабинетов
            for r_type, w_list in workloads_by_type.items():
                # Достаем переменные, которые претендуют на этот тип в этот слот
                vars_in_slot = []
                for w in w_list:
                    if (w.id, s.id) in self.time_vars:
                        vars_in_slot.append(self.time_vars[(w.id, s.id)])

                if not vars_in_slot: continue

                # Лимит комнат этого типа
                limit = room_capacities.get(r_type, 0)

                # Если спец. кабинетов (химия) нет, используем обычные (fallback)
                # Но если это Физра (GYM), то fallback запрещен
                if limit == 0:
                    if r_type == RoomType.GYM:
                        # Если спортзалов нет - это ошибка данных, но солвер должен выжить
                        self.model.Add(sum(vars_in_slot) == 0)
                        print(f"⚠️ ВНИМАНИЕ: Нет спортзалов для урока в слот {s.id}")
                        continue
                    else:
                        # Используем обычные классы вместо химии, если нет хим.кабинетов
                        limit = room_capacities.get(RoomType.STANDARD, 0)

                self.model.Add(sum(vars_in_slot) <= limit)

        # ==========================================
        # 4. ПОИСК РЕШЕНИЯ
        # ==========================================
        print(f"⏳ Решаем... (Максимум {self.solver.parameters.max_time_in_seconds} сек)")
        status = self.solver.Solve(self.model)

        end_time = time.time()
        duration = end_time - start_time
        print(f"⏱ Расчет занял: {duration:.2f} сек. Статус: {self.solver.StatusName(status)}")

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(f"✅ Решение найдено! Оценка счастья: {self.solver.ObjectiveValue()}")
            self._assign_rooms_greedy(workloads, slots, rooms)
            return True
        else:
            print("💥 Не удалось найти валидное расписание. Проверьте входные данные (мало учителей/комнат).")
            return False

    def _assign_rooms_greedy(self, workloads, slots, rooms):
        """
        Простой алгоритм раздачи комнат после того, как время утверждено.
        """
        final_schedule = []

        # Получаем список (w_id, s_id), которые состоялись
        active_assignments = []
        for (wid, sid), var in self.time_vars.items():
            if self.solver.Value(var):
                active_assignments.append((wid, sid))

        # Группируем по слотам, чтобы раздавать комнаты в конкретное время
        from collections import defaultdict
        slots_map = defaultdict(list)
        for wid, sid in active_assignments:
            slots_map[sid].append(wid)

        workloads_map = {w.id: w for w in workloads}
        rooms_map = {r.id: r for r in rooms}

        print("🏠 Распределяем кабинеты...")

        for sid, w_ids in slots_map.items():
            # Копия списка свободных комнат для этого слота
            available_rooms = list(rooms_map.values())

            # Сортируем уроки: Сначала спец. предметы (Физра, Химия), потом обычные
            # Это жадный алгоритм: важным - лучшее.
            current_workloads = [workloads_map[wid] for wid in w_ids]
            current_workloads.sort(key=lambda w: 0 if w.required_room_type != RoomType.STANDARD else 1)

            for w in current_workloads:
                needed_type = w.required_room_type

                # Ищем идеально подходящую комнату
                candidates = [r for r in available_rooms if r.room_type == needed_type]

                # Если не нашли и это не физра - берем обычный класс
                if not candidates and needed_type != RoomType.GYM:
                    candidates = [r for r in available_rooms if r.room_type == RoomType.STANDARD]

                if candidates:
                    # NOTE: Тут можно добавить логику "Закрепленный кабинет учителя"
                    chosen_room = candidates[0]
                    available_rooms.remove(chosen_room)  # Комната занята

                    entry = ScheduleEntry(
                        workload_id=w.id,
                        timeslot_id=sid,
                        room_id=chosen_room.id
                    )
                    final_schedule.append(entry)
                else:
                    print(f"⚠️ Не хватило комнаты для {w.subject} (ID: {w.id}) в слот {sid}")

        # Сохраняем в БД
        db.session.query(ScheduleEntry).delete()
        db.session.add_all(final_schedule)
        db.session.commit()
        print(f"💾 Сохранено {len(final_schedule)} уроков в базу данных.")