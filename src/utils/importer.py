import pandas as pd
from src.extensions import db
from src.models.school import School, Teacher, Subject, Room
from src.models.schedule import StudentGroup, Workload, ScheduleEntry
from src.models.enums import RoomType, SubgroupType


def import_rooms_from_file(filepath):
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip().lower() for c in df.columns]

    school = School.query.first()
    if not school:
        school = School(name="Universal School")
        db.session.add(school)
        db.session.commit()

    # Очистка
    db.session.query(ScheduleEntry).delete()
    db.session.query(Room).delete()
    db.session.commit()

    col_map = {'название': 'name', 'name': 'name', 'вместимость': 'capacity', 'capacity': 'capacity',
               'корпус': 'building', 'building': 'building', 'тип': 'type', 'type': 'type'}

    count = 0
    for index, row in df.iterrows():
        # Простая логика извлечения
        name = str(row.get('name') or row.get('Name') or f"Room-{index}")
        # Пропускаем пустые строки
        if name == 'nan': continue

        cap = 30
        if 'capacity' in df.columns: cap = int(row['capacity'])

        bld = ""
        if 'building' in df.columns: bld = str(row['building'])

        rtype = RoomType.STANDARD
        type_str = str(row.get('type') or row.get('Type') or '').lower()
        if 'gym' in type_str:
            rtype = RoomType.GYM
        elif 'it' in type_str:
            rtype = RoomType.IT_LAB
        elif 'chem' in type_str:
            rtype = RoomType.LAB_CHEMISTRY
        elif 'phys' in type_str:
            rtype = RoomType.LAB_PHYSICS
        elif 'bio' in type_str:
            rtype = RoomType.LAB_BIO

        room = Room(name=name, capacity=cap, building=bld, room_type=rtype, school_id=school.id)
        db.session.add(room)
        count += 1

    db.session.commit()
    return count


def import_data_from_file(filepath):
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip().lower() for c in df.columns]

    # Очистка
    db.session.query(ScheduleEntry).delete()
    db.session.query(Workload).delete()
    db.session.commit()  # Важный коммит перед загрузкой

    school = School.query.first()

    # Кэши
    subjects_cache = {s.name: s for s in Subject.query.all()}
    groups_cache = {g.name: g for g in StudentGroup.query.all()}
    teacher_objs = {t.name: t for t in Teacher.query.all()}

    count = 0
    # Маппинг колонок (упрощенный)
    for index, row in df.iterrows():
        t_name = row.get('teacher')
        if pd.isna(t_name): continue  # Пропуск пустых строк

        t_name = str(t_name).strip()
        s_name = str(row.get('subject', 'General')).strip()
        c_name = str(row.get('class', '1-A')).strip()
        hours = int(row.get('hours', 1))

        # 1. УЧИТЕЛЬ
        selected_teacher = None
        if t_name.lower() in ['auto', 'nan', 'none', '']:
            vac_name = f"Вакансия ({s_name})"
            if vac_name not in teacher_objs:
                vac = Teacher(name=vac_name, school_id=school.id, is_vacancy=True, max_hours=999)
                db.session.add(vac)
                teacher_objs[vac_name] = vac
            selected_teacher = teacher_objs[vac_name]
        else:
            if t_name not in teacher_objs:
                t = Teacher(name=t_name, school_id=school.id)
                # Max Hours check
                mh = row.get('maxhours') or row.get('max_hours')
                if pd.notna(mh): t.max_hours = int(mh)
                db.session.add(t)
                teacher_objs[t_name] = t
            selected_teacher = teacher_objs[t_name]

        # 2. ПРЕДМЕТ
        if s_name not in subjects_cache:
            s = Subject(name=s_name, school_id=school.id)
            db.session.add(s)
            subjects_cache[s_name] = s
        subject = subjects_cache[s_name]

        # 3. КЛАСС
        if c_name not in groups_cache:
            shift = int(row.get('shift', 1))
            g = StudentGroup(name=c_name, shift=shift, school_id=school.id)
            db.session.add(g)
            groups_cache[c_name] = g
        group = groups_cache[c_name]

        # 4. ДЕТАЛИ
        sub = SubgroupType.WHOLE_CLASS
        sub_val = str(row.get('subgroup', '')).lower()
        if '1' in sub_val:
            sub = SubgroupType.GROUP_1
        elif '2' in sub_val:
            sub = SubgroupType.GROUP_2

        rtype = RoomType.STANDARD
        rt_val = str(row.get('roomtype', '')).lower()
        if 'gym' in rt_val:
            rtype = RoomType.GYM
        elif 'phys' in rt_val:
            rtype = RoomType.LAB_PHYSICS

        w = Workload(school_id=school.id, teacher=selected_teacher, subject=subject, group=group, hours_per_week=hours,
                     subgroup=sub, required_room_type=rtype)
        db.session.add(w)
        count += 1

    db.session.commit()
    return count