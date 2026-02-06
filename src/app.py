from flask import Flask, render_template
from src.config import Config
from src.extensions import db, migrate
from src.commands import register_commands
from src.api.debug import debug_bp

# Импорты моделей, необходимых для роута расписания
from src.models.schedule import Workload, TimeSlot, StudentGroup
from src.models.school import Room, Subject, Teacher
from src.solver.engine import SchoolScheduler


def create_app(config_class=Config):
    """Factory Pattern для создания приложения"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Инициализация расширений
    db.init_app(app)
    migrate.init_app(app, db)

    # 2. Регистрация команд (CLI)
    register_commands(app)

    # 3. Регистрация Blueprints (Роуты)
    app.register_blueprint(debug_bp)

    @app.route('/')
    def index():
        return {
            "message": "School Scheduler Pro API is Running",
            "ui_link": "/schedule",
            "debug_link": "/debug/generate-test/1"
        }

    @app.route('/schedule')
    def show_schedule():
        # 1. Загружаем данные для решателя
        school_id = 1
        workloads = Workload.query.filter_by(school_id=school_id).all()
        slots = TimeSlot.query.filter_by(school_id=school_id).all()
        rooms = Room.query.filter_by(school_id=school_id).all()

        # 2. Подгружаем справочники для красивого отображения (ID -> Имя)
        subjects_map = {s.id: s.name for s in Subject.query.filter_by(school_id=school_id).all()}
        teachers_map = {t.id: t.name for t in Teacher.query.filter_by(school_id=school_id).all()}
        groups_map = {g.id: g.name for g in StudentGroup.query.filter_by(school_id=school_id).all()}

        # 3. Запускаем решатель
        solver = SchoolScheduler(school_id)
        raw_schedule = solver.run_algorithm(workloads, slots, rooms)

        if not raw_schedule:
            return "Не удалось составить расписание (конфликт ограничений)", 400

        # 4. Преобразуем список в удобную сетку: grid[(day, period)] = [Lesson1, Lesson2]
        schedule_grid = {}

        for item in raw_schedule:
            slot = item['slot']
            w = item['workload']
            r = item['room']

            key = (slot.day_of_week, slot.period_number)
            if key not in schedule_grid:
                schedule_grid[key] = []

            schedule_grid[key].append({
                "subject": subjects_map.get(w.subject_id, "Unknown"),
                "teacher": teachers_map.get(w.teacher_id, "Unknown"),
                "group": groups_map.get(w.group_id, "Unknown"),
                "room": r.name
            })

        return render_template('schedule.html', schedule_grid=schedule_grid)

    return app