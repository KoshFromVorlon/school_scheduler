import os
from flask import Flask, render_template, redirect, url_for, request
from werkzeug.utils import secure_filename
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView

from src.config import Config
from src.extensions import db, migrate
from src.commands import register_commands
from src.api.debug import debug_bp

from src.models.schedule import Workload, TimeSlot, StudentGroup, ScheduleEntry
from src.models.school import Room, Subject, Teacher, School
from src.models.enums import SubgroupType
from src.solver.engine import SchoolScheduler
from src.utils.importer import import_data_from_file, import_rooms_from_file


# --- АДМИНКА ---
class WorkloadView(ModelView):
    column_list = ['subject', 'group', 'teacher', 'hours_per_week']


class ScheduleEntryView(ModelView):
    column_list = ['timeslot', 'workload', 'room']


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['UPLOAD_FOLDER'] = 'uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    register_commands(app)

    admin = Admin(app, name='School Scheduler', template_mode='bootstrap4')
    admin.add_view(ModelView(Teacher, db.session, name="Учителя"))
    admin.add_view(ModelView(StudentGroup, db.session, name="Классы"))
    admin.add_view(ScheduleEntryView(ScheduleEntry, db.session, name="Сетка"))

    # === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
    def build_grid(entries):
        grid = {}
        subjects = {s.id: s.name for s in Subject.query.all()}
        teachers = {t.id: t.name for t in Teacher.query.all()}
        groups = {g.id: g.name for g in StudentGroup.query.all()}
        rooms = {r.id: r.name for r in Room.query.all()}
        workloads = {w.id: w for w in Workload.query.all()}
        slots = {s.id: s for s in TimeSlot.query.all()}

        for entry in entries:
            w = workloads.get(entry.workload_id)
            s = slots.get(entry.timeslot_id)
            r_name = rooms.get(entry.room_id, "?")
            if not w or not s: continue

            key = (s.day_of_week, s.period_number)
            if key not in grid: grid[key] = []

            subj_name = subjects.get(w.subject_id, "?")
            if w.subgroup == SubgroupType.GROUP_1:
                subj_name += " (Гр. 1)"
            elif w.subgroup == SubgroupType.GROUP_2:
                subj_name += " (Гр. 2)"

            grid[key].append({
                "subject": subj_name,
                "teacher": teachers.get(w.teacher_id, "?"),
                "group": groups.get(w.group_id, "?"),
                "room": r_name
            })
        return grid

    # === УМНОЕ МЕНЮ (НАТУРАЛЬНАЯ СОРТИРОВКА) ===
    @app.context_processor
    def inject_menus():
        try:
            # 1. ПОЛУЧАЕМ ДАННЫЕ
            teachers = Teacher.query.all()
            groups = StudentGroup.query.all()

            # 2. СОРТИРОВКА УЧИТЕЛЕЙ (1, 2, 10 + Вакансии в конце)
            def teacher_sort_key(t):
                name = t.name.strip()
                lower_name = name.lower()

                # А. ОПРЕДЕЛЯЕМ ПРЕДМЕТ (Группировка)
                subject = name
                is_vacancy = 0  # 0 = Учитель (сверху), 1 = Вакансия (снизу)

                if t.is_vacancy or "вакансия" in lower_name:
                    is_vacancy = 1
                    if "(" in name and ")" in name:
                        start = name.find('(') + 1
                        end = name.find(')')
                        subject = name[start:end].strip()
                    else:
                        subject = name
                elif "_" in name:
                    subject = name.split('_')[0].strip()

                # Б. ИЗВЛЕКАЕМ НОМЕР (Для Teach_1, Teach_2, Teach_10)
                number = 0
                parts = name.split('_')
                if len(parts) > 1 and parts[-1].isdigit():
                    number = int(parts[-1])  # Превращаем "10" в число 10

                # В. КЛЮЧ СОРТИРОВКИ:
                # 1. Предмет (Английский вместе)
                # 2. Вакансия? (Люди выше вакансий)
                # 3. Номер (2 < 10)
                # 4. Имя (на случай если номеров нет)
                return (subject.lower(), is_vacancy, number, name)

            teachers.sort(key=teacher_sort_key)

            # 3. СОРТИРОВКА КЛАССОВ (1, 2 ... 10, 11)
            def group_sort_key(g):
                try:
                    parts = g.name.split('-')
                    if len(parts) >= 2 and parts[0].isdigit():
                        return (int(parts[0]), parts[1])
                    if g.name.isdigit(): return (int(g.name), "")
                    return (999, g.name)
                except:
                    return (999, g.name)

            groups.sort(key=group_sort_key)

            return dict(all_teachers=teachers, all_groups=groups)
        except Exception as e:
            print(f"!!! ОШИБКА В МЕНЮ: {e}")
            return dict(all_teachers=[], all_groups=[])

    # === ДИАГНОСТИКА ===
    @app.route('/check')
    def check_db():
        t_count = Teacher.query.count()
        g_count = StudentGroup.query.count()
        r_count = Room.query.count()
        w_count = Workload.query.count()

        teachers = Teacher.query.limit(10).all()
        t_list = "<br>".join([t.name for t in teachers])

        return f"""
        <h1>Диагностика базы данных</h1>
        <ul>
            <li><b>Учителя:</b> {t_count}</li>
            <li><b>Классы:</b> {g_count}</li>
            <li><b>Комнаты:</b> {r_count}</li>
            <li><b>Нагрузка:</b> {w_count}</li>
        </ul>
        <h3>Первые 10 учителей:</h3>
        {t_list}
        <br><br>
        <a href="/">На главную</a>
        """

    @app.route('/')
    def index():
        return render_template('schedule.html', schedule_grid=None, title="Добро пожаловать")

    @app.route('/teacher/<int:teacher_id>')
    def show_teacher_schedule(teacher_id):
        teacher = Teacher.query.get_or_404(teacher_id)
        entries = ScheduleEntry.query.join(Workload).filter(Workload.teacher_id == teacher_id).all()
        grid = build_grid(entries)
        return render_template('schedule.html', schedule_grid=grid, title=f"Расписание: {teacher.name}",
                               show_group_name=True, show_teacher_name=False)

    @app.route('/group/<int:group_id>')
    def show_group_schedule(group_id):
        group = StudentGroup.query.get_or_404(group_id)
        entries = ScheduleEntry.query.join(Workload).filter(Workload.group_id == group_id).all()
        grid = build_grid(entries)
        return render_template('schedule.html', schedule_grid=grid, title=f"Расписание: {group.name}",
                               show_group_name=False, show_teacher_name=True)

    @app.route('/import', methods=['GET', 'POST'])
    def import_page():
        if request.method == 'POST':
            import_type = request.form.get('import_type')
            if 'file' not in request.files: return "Нет файла", 400
            file = request.files['file']
            if file.filename == '': return "Файл не выбран", 400

            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                msg = ""
                count = 0
                if import_type == 'rooms':
                    count = import_rooms_from_file(filepath)
                    msg = f"Инфраструктура: загружено {count} помещений."
                elif import_type == 'workload':
                    count = import_data_from_file(filepath)
                    msg = f"Нагрузка: загружено {count} записей."

                return render_template('import_success.html', message=msg)
            except Exception as e:
                return f"<h1>ОШИБКА ИМПОРТА:</h1><p>{str(e)}</p>", 500
        return render_template('import.html')

    @app.route('/generate', methods=['POST'])
    def generate_schedule():
        school_id = 1
        workloads = Workload.query.filter_by(school_id=school_id).all()
        slots = TimeSlot.query.filter_by(school_id=school_id).all()
        rooms = Room.query.filter_by(school_id=school_id).all()

        if not workloads: return "Ошибка: База нагрузки пуста!", 400

        solver = SchoolScheduler(school_id)
        if solver.run_algorithm(workloads, slots, rooms):
            return redirect(url_for('index'))
        else:
            return "Не удалось составить расписание", 400

    return app