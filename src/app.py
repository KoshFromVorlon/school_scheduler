import os
from flask import Flask, render_template, redirect, url_for, request, flash
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

# ИМПОРТ ФУНКЦИЙ ЗАГРУЗКИ (ТЕПЕРЬ ОБЕ)
from src.utils.importer import import_data_from_file, import_rooms_from_file


# --- АДМИНКА ---
class WorkloadView(ModelView):
    column_list = ['subject', 'group', 'subgroup', 'teacher', 'hours_per_week', 'required_room_type']
    column_labels = {'subject': 'Предмет', 'group': 'Класс', 'subgroup': 'Подгруппа', 'teacher': 'Учитель',
                     'required_room_type': 'Тип кабинета'}


class ScheduleEntryView(ModelView):
    column_list = ['timeslot', 'workload', 'room']


class TimeSlotView(ModelView):
    column_list = ['day_of_week', 'period_number', 'shift_number']
    column_labels = {'day_of_week': 'День', 'period_number': 'Урок', 'shift_number': 'Смена'}

    def _format_day(view, context, model, name):
        days = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт"}
        return days.get(model.day_of_week, str(model.day_of_week))

    column_formatters = {'day_of_week': _format_day}


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Папка для временных файлов
    app.config['UPLOAD_FOLDER'] = 'uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    register_commands(app)
    app.register_blueprint(debug_bp)

    admin = Admin(app, name='School Scheduler', template_mode='bootstrap4')
    admin.add_view(ModelView(School, db.session, name="Школы"))
    admin.add_view(ModelView(Teacher, db.session, name="Учителя"))
    admin.add_view(ModelView(Subject, db.session, name="Предметы"))
    admin.add_view(ModelView(Room, db.session, name="Кабинеты"))
    admin.add_view(ModelView(StudentGroup, db.session, name="Классы"))
    admin.add_view(WorkloadView(Workload, db.session, name="Нагрузка"))
    admin.add_view(TimeSlotView(TimeSlot, db.session, name="Слоты"))
    admin.add_view(ScheduleEntryView(ScheduleEntry, db.session, name="Результат"))

    # ГЕНЕРАТОР СЕТКИ
    def build_schedule_grid(entries):
        subjects = {s.id: s.name for s in Subject.query.all()}
        teachers = {t.id: t.name for t in Teacher.query.all()}
        groups = {g.id: g.name for g in StudentGroup.query.all()}
        rooms = {r.id: r.name for r in Room.query.all()}
        workloads = {w.id: w for w in Workload.query.all()}
        slots = {s.id: s for s in TimeSlot.query.all()}

        grid = {}
        for entry in entries:
            w = workloads.get(entry.workload_id)
            s = slots.get(entry.timeslot_id)
            if not w or not s: continue
            key = (s.day_of_week, s.period_number)
            if key not in grid: grid[key] = []

            subj_name = subjects.get(w.subject_id, "?")
            subgroup_label = ""
            if w.subgroup == SubgroupType.GROUP_1:
                subgroup_label = "(Гр. 1)"
            elif w.subgroup == SubgroupType.GROUP_2:
                subgroup_label = "(Гр. 2)"

            grid[key].append({
                "subject": f"{subj_name} {subgroup_label}",
                "teacher": teachers.get(w.teacher_id, "?"),
                "group": groups.get(w.group_id, "?"),
                "room": rooms.get(entry.room_id, "?"),
            })
        return grid

    @app.context_processor
    def inject_menus():
        return dict(
            all_teachers=Teacher.query.order_by(Teacher.name).all(),
            all_groups=StudentGroup.query.order_by(StudentGroup.name).all()
        )

    @app.route('/')
    def index():
        entries = ScheduleEntry.query.all()
        grid = build_schedule_grid(entries)
        return render_template('schedule.html', schedule_grid=grid, title="Общее расписание", show_teacher_name=True,
                               show_group_name=True)

    @app.route('/teacher/<int:teacher_id>')
    def show_teacher_schedule(teacher_id):
        entries = ScheduleEntry.query.join(Workload).filter(Workload.teacher_id == teacher_id).all()
        teacher = Teacher.query.get_or_404(teacher_id)
        grid = build_schedule_grid(entries)
        return render_template('schedule.html', schedule_grid=grid, title=f"Расписание: {teacher.name}",
                               show_teacher_name=False, show_group_name=True)

    @app.route('/group/<int:group_id>')
    def show_group_schedule(group_id):
        entries = ScheduleEntry.query.join(Workload).filter(Workload.group_id == group_id).all()
        group = StudentGroup.query.get_or_404(group_id)
        grid = build_schedule_grid(entries)
        return render_template('schedule.html', schedule_grid=grid, title=f"Расписание: {group.name}",
                               show_teacher_name=True, show_group_name=False)

    # === ОБНОВЛЕННЫЙ МАРШРУТ ИМПОРТА ===
    @app.route('/import', methods=['GET', 'POST'])
    def import_page():
        if request.method == 'POST':
            # Получаем тип импорта из скрытого поля формы
            import_type = request.form.get('import_type')

            if 'file' not in request.files:
                return "Нет файла", 400
            file = request.files['file']
            if file.filename == '':
                return "Файл не выбран", 400

            if file:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                # ЗАПУСК ИМПОРТА (Разветвление логики)
                try:
                    count = 0
                    msg = ""

                    if import_type == 'rooms':
                        # Импорт инфраструктуры
                        count = import_rooms_from_file(filepath)
                        msg = f"Успешно создано {count} помещений (инфраструктура)."
                    elif import_type == 'workload':
                        # Импорт нагрузки
                        count = import_data_from_file(filepath)
                        msg = f"Успешно загружено {count} записей нагрузки."
                    else:
                        # Fallback (если вдруг тип не передан)
                        count = import_data_from_file(filepath)
                        msg = f"Импортировано {count} записей."

                    return render_template('import_success.html', count=count, message=msg)

                except Exception as e:
                    return f"Ошибка импорта: {str(e)}", 500

        return render_template('import.html')

    # =======================================

    @app.route('/generate', methods=['POST'])
    def generate_schedule():
        school_id = 1
        workloads = Workload.query.filter_by(school_id=school_id).all()
        slots = TimeSlot.query.filter_by(school_id=school_id).all()
        rooms = Room.query.filter_by(school_id=school_id).all()

        solver = SchoolScheduler(school_id)
        if solver.run_algorithm(workloads, slots, rooms):
            return redirect(url_for('index'))
        else:
            return "Не удалось составить расписание (Конфликт)", 400

    return app