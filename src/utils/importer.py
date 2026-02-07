import pandas as pd
from src.extensions import db
from src.models.school import School, Teacher, Subject, Room
from src.models.schedule import StudentGroup, Workload
from src.models.enums import RoomType, SubgroupType


def import_rooms_from_file(filepath):
    """ИМПОРТ КАБИНЕТОВ (Инфраструктура)."""
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip().lower() for c in df.columns]

    col_map = {
        'название': 'name', 'name': 'name', 'room': 'name',
        'тип': 'type', 'type': 'type', 'roomtype': 'type',
        'вместимость': 'capacity', 'capacity': 'capacity',
        'корпус': 'building', 'building': 'building'
    }

    school = School.query.first()
    if not school:
        school = School(name="Universal School")
        db.session.add(school)
        db.session.commit()

    db.session.query(Room).delete()

    count = 0
    for index, row in df.iterrows():
        def get_val(rus_keys, default=None):
            for k in rus_keys:
                found_col = next((c for c in df.columns if col_map.get(c) == k), None)
                if found_col: return row[found_col] if pd.notna(row[found_col]) else default
            return default

        name = str(get_val(['name'], f"Room-{index}"))
        capacity = int(get_val(['capacity'], 30))
        building = str(get_val(['building'], ""))
        type_raw = str(get_val(['type'], 'standard')).lower()

        r_type = RoomType.STANDARD
        if 'gym' in type_raw:
            r_type = RoomType.GYM
        elif 'it' in type_raw:
            r_type = RoomType.IT_LAB
        elif 'chem' in type_raw:
            r_type = RoomType.LAB_CHEMISTRY
        elif 'phys' in type_raw:
            r_type = RoomType.LAB_PHYSICS
        elif 'bio' in type_raw:
            r_type = RoomType.LAB_BIO

        room = Room(name=name, capacity=capacity, building=building, room_type=r_type, school_id=school.id)
        db.session.add(room)
        count += 1
    db.session.commit()
    return count


def import_data_from_file(filepath):
    """ИМПОРТ НАГРУЗКИ С ПОДДЕРЖКОЙ ВАКАНСИЙ."""
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip().lower() for c in df.columns]

    col_map = {
        'учитель': 'teacher', 'teacher': 'teacher',
        'предмет': 'subject', 'subject': 'subject',
        'класс': 'class', 'class': 'class',
        'часов': 'hours', 'hours': 'hours',
        'лимит': 'maxhours', 'maxhours': 'maxhours', 'max_hours': 'maxhours',  # Новая колонка
        'подгруппа': 'subgroup', 'subgroup': 'subgroup',
        'кабинет': 'roomtype', 'room_type': 'roomtype',
        'смена': 'shift', 'shift': 'shift'
    }

    db.session.query(Workload).delete()

    school = School.query.first()
    if not school:
        school = School(name="My School")
        db.session.add(school)
        db.session.commit()

    subjects_cache = {s.name: s for s in Subject.query.all()}
    groups_cache = {g.name: g for g in StudentGroup.query.all()}

    # Кэш учителей (включая вакансии)
    teacher_objs = {t.name: t for t in Teacher.query.all()}

    count = 0

    for index, row in df.iterrows():
        def get_val(rus_keys, default=None):
            for k in rus_keys:
                found_col = next((c for c in df.columns if col_map.get(c) == k), None)
                if found_col: return row[found_col] if pd.notna(row[found_col]) else default
            return default

        teacher_name_raw = get_val(['teacher'])
        subject_name = str(get_val(['subject'], 'General'))
        class_name = str(get_val(['class'], '1-A'))
        hours = int(get_val(['hours'], 1))
        max_hours_val = get_val(['maxhours'])  # Лимит из файла

        sub_raw = str(get_val(['subgroup'], 'whole')).lower().strip()
        subgroup = SubgroupType.WHOLE_CLASS
        if '1' in sub_raw:
            subgroup = SubgroupType.GROUP_1
        elif '2' in sub_raw:
            subgroup = SubgroupType.GROUP_2

        room_raw = str(get_val(['roomtype'], 'standard')).lower()
        r_type = RoomType.STANDARD
        if 'gym' in room_raw:
            r_type = RoomType.GYM
        elif 'it' in room_raw:
            r_type = RoomType.IT_LAB
        elif 'chem' in room_raw:
            r_type = RoomType.LAB_CHEMISTRY
        elif 'phys' in room_raw:
            r_type = RoomType.LAB_PHYSICS
        elif 'bio' in room_raw:
            r_type = RoomType.LAB_BIO

        shift = int(get_val(['shift'], 1))

        # --- 1. ВЫБОР УЧИТЕЛЯ ИЛИ ВАКАНСИИ ---
        selected_teacher = None

        # Проверяем, указано ли имя (или это Auto/Empty)
        is_auto = False
        if not teacher_name_raw or str(teacher_name_raw).lower() in ['auto', 'nan', 'none', '']:
            is_auto = True

        if not is_auto:
            # РЕАЛЬНЫЙ УЧИТЕЛЬ
            real_name = str(teacher_name_raw).strip()
            if real_name not in teacher_objs:
                t = Teacher(name=real_name, school_id=school.id)
                db.session.add(t)
                teacher_objs[real_name] = t

            selected_teacher = teacher_objs[real_name]
            # Обновляем лимит, если он пришел в файле
            if max_hours_val is not None:
                try:
                    selected_teacher.max_hours = int(max_hours_val)
                except:
                    pass
        else:
            # ВАКАНСИЯ
            vac_name = f"Вакансия ({subject_name})"
            if vac_name not in teacher_objs:
                # Вакансия безлимитна (999 часов)
                vac = Teacher(name=vac_name, school_id=school.id, is_vacancy=True, max_hours=999)
                db.session.add(vac)
                teacher_objs[vac_name] = vac
            selected_teacher = teacher_objs[vac_name]

        # --- 2. ПРЕДМЕТ И КЛАСС ---
        if subject_name not in subjects_cache:
            s = Subject(name=subject_name, school_id=school.id)
            db.session.add(s)
            subjects_cache[subject_name] = s
        subject = subjects_cache[subject_name]

        if class_name not in groups_cache:
            g = StudentGroup(name=class_name, shift=shift, school_id=school.id)
            db.session.add(g)
            groups_cache[class_name] = g
        group = groups_cache[class_name]

        # --- 3. СОЗДАНИЕ ЗАПИСИ ---
        w = Workload(
            school_id=school.id, teacher=selected_teacher, subject=subject, group=group,
            hours_per_week=hours, subgroup=subgroup, required_room_type=r_type
        )
        db.session.add(w)
        count += 1

    db.session.commit()
    return count