from ortools.sat.python import cp_model
from src.extensions import db
from src.models.schedule import ScheduleEntry
from src.models.enums import RoomType, SubgroupType


class SchoolScheduler:
    def __init__(self, school_id):
        self.school_id = school_id
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Настройки: 8 потоков, 60 секунд макс (задача стала сложнее)
        self.solver.parameters.max_time_in_seconds = 600.0
        self.solver.parameters.num_search_workers = 8
        self.solver.parameters.log_search_progress = True

        self.grid = {}

    def run_algorithm(self, workloads, slots, rooms):
        # Сортируем для детерминизма
        workloads = sorted(workloads, key=lambda x: x.id)
        slots = sorted(slots, key=lambda x: (x.day_of_week, x.period_number))
        rooms = sorted(rooms, key=lambda x: x.id)

        # === 1. Создание переменных ===
        # Создаем переменную ТОЛЬКО если кабинет подходит по типу
        for w in workloads:
            for s in slots:
                for r in rooms:
                    # ЖЕСТКИЙ ФИЛЬТР: Нельзя проводить Физру в Хим.кабинете
                    if w.required_room_type != r.room_type:
                        continue

                    name = f'w{w.id}_d{s.day_of_week}_p{s.period_number}_r{r.id}'
                    self.grid[(w.id, s.id, r.id)] = self.model.NewBoolVar(name)

        # === 2. Ограничения ===

        # А. Выполнить план часов (hours_per_week)
        for w in workloads:
            lessons = []
            for s in slots:
                for r in rooms:
                    if (w.id, s.id, r.id) in self.grid:
                        lessons.append(self.grid[(w.id, s.id, r.id)])

            if lessons:
                self.model.Add(sum(lessons) == w.hours_per_week)
            else:
                print(f"⚠️ ВНИМАНИЕ: Для предмета {w.subject} нет подходящих кабинетов!")

        # Б. Учитель: не может вести 2 урока одновременно
        teacher_workloads = {}
        for w in workloads:
            teacher_workloads.setdefault(w.teacher_id, []).append(w)

        for t_workloads in teacher_workloads.values():
            for s in slots:
                concurrent_lessons = []
                for w in t_workloads:
                    for r in rooms:
                        if (w.id, s.id, r.id) in self.grid:
                            concurrent_lessons.append(self.grid[(w.id, s.id, r.id)])
                self.model.Add(sum(concurrent_lessons) <= 1)

        # В. Кабинет: только 1 урок одновременно
        for s in slots:
            for r in rooms:
                lessons_in_room = []
                for w in workloads:
                    if (w.id, s.id, r.id) in self.grid:
                        lessons_in_room.append(self.grid[(w.id, s.id, r.id)])
                self.model.Add(sum(lessons_in_room) <= 1)

        # Г. ГРУППЫ И ПОДГРУППЫ (Сложная логика)
        # Группируем нагрузки по Классам (5-А, 8-Б...)
        group_workloads_map = {}
        for w in workloads:
            group_workloads_map.setdefault(w.group_id, []).append(w)

        for g_id, g_workloads in group_workloads_map.items():
            for s in slots:
                # Собираем переменные для этого класса в этот слот
                # Разделяем их по типу подгруппы
                vars_whole = []
                vars_subgroups = {}  # 'group_1': [v1, v2], 'group_2': [v3]

                for w in g_workloads:
                    # Собираем все варианты кабинетов для этой нагрузки
                    w_lessons = []
                    for r in rooms:
                        if (w.id, s.id, r.id) in self.grid:
                            w_lessons.append(self.grid[(w.id, s.id, r.id)])

                    if not w_lessons: continue

                    # Сумма (активен ли урок w в этот слот)
                    # Обычно w_active - это 0 или 1, так как учитель/кабинет уже ограничены
                    w_active = sum(w_lessons)

                    if w.subgroup == SubgroupType.WHOLE_CLASS:
                        vars_whole.append(w_active)
                    else:
                        vars_subgroups.setdefault(w.subgroup.value, []).append(w_active)

                # ОГРАНИЧЕНИЕ 1: Если идет урок у ВСЕГО класса, подгруппы отдыхают
                # И наоборот: Если занята подгруппа, урок для всего класса невозможен
                # sum(Whole) + sum(AnySubgroup) <= 1

                sum_whole = sum(vars_whole)

                # Проверяем конфликт "Весь класс" vs "Каждая подгруппа"
                for sub_vars in vars_subgroups.values():
                    self.model.Add(sum_whole + sum(sub_vars) <= 1)

                # ОГРАНИЧЕНИЕ 2: Одна подгруппа не может быть в двух местах (уже покрыто логикой учителя/кабинета, но на всякий случай)
                for sub_vars in vars_subgroups.values():
                    self.model.Add(sum(sub_vars) <= 1)

                self.model.Add(sum_whole <= 1)

                # ВАЖНО: Мы НЕ запрещаем Group 1 и Group 2 идти одновременно.
                # Мы не пишем sum(group1) + sum(group2) <= 1. Это разрешено!

        # === 3. Решение ===
        status = self.solver.Solve(self.model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(f"✅ Решение найдено! ({self.solver.WallTime():.2f} сек)")
            self._save_to_db(workloads, slots, rooms)
            return True
        else:
            print("💥 Невозможно составить расписание. Конфликт условий.")
            return False

    def _save_to_db(self, workloads, slots, rooms):
        db.session.query(ScheduleEntry).delete()
        new_entries = []
        for w in workloads:
            for s in slots:
                for r in rooms:
                    if (w.id, s.id, r.id) in self.grid:
                        if self.solver.Value(self.grid[(w.id, s.id, r.id)]):
                            new_entries.append(ScheduleEntry(
                                workload_id=w.id, timeslot_id=s.id, room_id=r.id
                            ))
        db.session.add_all(new_entries)
        db.session.commit()