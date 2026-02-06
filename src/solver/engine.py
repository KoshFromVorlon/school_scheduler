from ortools.sat.python import cp_model


class SchoolScheduler:
    def __init__(self, school_id):
        self.school_id = school_id
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        # Лимиты для OR-Tools (чтобы не завис на вечность)
        self.solver.parameters.max_time_in_seconds = 30.0
        self.grid = {}

    def run_algorithm(self, workloads, slots, rooms):
        """
        :param workloads: QuerySet или список Workload
        :param slots: QuerySet или список TimeSlot
        :param rooms: QuerySet или список Room
        :return: Список словарей с решением или None
        """

        # === 1. Создание переменных ===
        # x[workload, slot, room] = 1 (если урок проводится), иначе 0
        for w in workloads:
            for s in slots:
                for r in rooms:
                    # Создаем булеву переменную
                    self.grid[(w.id, s.id, r.id)] = self.model.NewBoolVar(f'w{w.id}_s{s.id}_r{r.id}')

        # === 2. Ограничения (Hard Constraints) ===

        # А. Каждый предмет (нагрузка) должен быть проведен ровно hours_per_week раз
        for w in workloads:
            lessons = []
            for s in slots:
                for r in rooms:
                    lessons.append(self.grid[(w.id, s.id, r.id)])
            self.model.Add(sum(lessons) == w.hours_per_week)

        # Б. Учитель не может вести два урока одновременно
        # Сначала сгруппируем нагрузки по учителям
        teacher_workloads = {}
        for w in workloads:
            if w.teacher_id not in teacher_workloads:
                teacher_workloads[w.teacher_id] = []
            teacher_workloads[w.teacher_id].append(w)

        for t_id, t_workloads in teacher_workloads.items():
            for s in slots:  # Для каждого слота времени
                concurrent_lessons = []
                for w in t_workloads:
                    for r in rooms:  # Во всех кабинетах
                        concurrent_lessons.append(self.grid[(w.id, s.id, r.id)])
                # Сумма уроков учителя в этот слот времени <= 1
                self.model.Add(sum(concurrent_lessons) <= 1)

        # В. Один кабинет - один урок в одно время
        for s in slots:
            for r in rooms:
                lessons_in_room = []
                for w in workloads:
                    lessons_in_room.append(self.grid[(w.id, s.id, r.id)])
                self.model.Add(sum(lessons_in_room) <= 1)

        # Г. Группа не может быть на двух уроках одновременно
        group_workloads = {}
        for w in workloads:
            if w.group_id not in group_workloads:
                group_workloads[w.group_id] = []
            group_workloads[w.group_id].append(w)

        for g_id, g_workloads in group_workloads.items():
            for s in slots:
                concurrent_lessons = []
                for w in g_workloads:
                    for r in rooms:
                        concurrent_lessons.append(self.grid[(w.id, s.id, r.id)])
                self.model.Add(sum(concurrent_lessons) <= 1)

        # === 3. Решение ===
        status = self.solver.Solve(self.model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._format_solution(workloads, slots, rooms)
        return None

    def _format_solution(self, workloads, slots, rooms):
        results = []
        for w in workloads:
            for s in slots:
                for r in rooms:
                    if self.solver.Value(self.grid[(w.id, s.id, r.id)]):
                        results.append({
                            "workload": w,
                            "slot": s,
                            "room": r
                        })
        return results
