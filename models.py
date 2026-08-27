from sqlalchemy import CheckConstraint, Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from utils import now_utc


class TimestampSoftDeleteMixin:
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class TeacherSubject(Base, TimestampSoftDeleteMixin):
    __tablename__ = "teacher_subjects"
    __table_args__ = (
        UniqueConstraint("teacher_id", "subject_id", name="uq_teacher_subject"),
    )

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    is_assistant = Column(Boolean, default=False, nullable=False)

    teacher = relationship("User", back_populates="teacher_subject_links", foreign_keys=[teacher_id])
    subject = relationship("Subject", back_populates="teacher_subject_links")


class User(Base, TimestampSoftDeleteMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, index=True)  # 'student', 'teacher', 'owner', 'tutor'
    phone = Column(String, nullable=True)
    permissions = Column(Text, nullable=True)
    
    # حقول خاصة بالطلاب
    grade_level = Column(String, nullable=True)  # الصف الدراسي
    section_id = Column(Integer, ForeignKey("grade_sections.id"), nullable=True, index=True)
    group_id = Column(Integer, ForeignKey("section_groups.id"), nullable=True, index=True)
    
    # حقول خاصة بالمدرسين
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True)
    
    # حقول خاصة بالمدرسين الخصوصيين (Tutors)
    specialty = Column(String, nullable=True)
    hourly_rate = Column(Float, nullable=True)

    avatar_url = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    is_blocked = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_code = Column(String, nullable=True)
    verification_expires_at = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # العلاقات
    subject = relationship("Subject", foreign_keys=[subject_id], back_populates="teachers")
    teacher_subject_links = relationship("TeacherSubject", back_populates="teacher", foreign_keys="[TeacherSubject.teacher_id]")
    teaching_subjects = relationship(
        "Subject",
        secondary="teacher_subjects",
        primaryjoin="User.id == TeacherSubject.teacher_id",
        secondaryjoin="Subject.id == TeacherSubject.subject_id",
        viewonly=True,
    )
    enrollments = relationship("Enrollment", back_populates="student", foreign_keys="[Enrollment.student_id]", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="student", foreign_keys="[Submission.student_id]", cascade="all, delete-orphan")
    ratings_given = relationship("Rating", foreign_keys="[Rating.student_id]", back_populates="student")
    ratings_received = relationship("Rating", foreign_keys="[Rating.teacher_id]", back_populates="teacher")
    notifications = relationship("Notification", back_populates="user", foreign_keys="[Notification.user_id]", cascade="all, delete-orphan")
    password_resets = relationship("PasswordReset", back_populates="user", foreign_keys="[PasswordReset.user_id]", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    activities = relationship("UserActivity", back_populates="user", cascade="all, delete-orphan")
    grade_section = relationship("GradeSection", foreign_keys=[section_id])
    section_group = relationship("SectionGroup", foreign_keys=[group_id])


class Subject(Base, TimestampSoftDeleteMixin):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("name", "grade_level", name="uq_subject_name_grade"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    grade_level = Column(String, nullable=False)
    category = Column(String, nullable=True)
    grade = Column(String, nullable=True)
    semester = Column(String, nullable=True)
    thumbnail = Column(String, nullable=True)
    max_students = Column(Integer, nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    description = Column(Text, nullable=True)

    # العلاقات
    teachers = relationship("User", foreign_keys=[User.subject_id], back_populates="subject")
    teacher_subject_links = relationship("TeacherSubject", back_populates="subject")
    teacher_codes = relationship("TeacherCode", back_populates="subject", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="subject", cascade="all, delete-orphan")
    lectures = relationship("Lecture", back_populates="subject", cascade="all, delete-orphan")
    homeworks = relationship("Homework", back_populates="subject", cascade="all, delete-orphan")
    ratings = relationship("Rating", back_populates="subject", cascade="all, delete-orphan")
    prerequisites = relationship("SubjectPrerequisite", foreign_keys="[SubjectPrerequisite.subject_id]", back_populates="subject", cascade="all, delete-orphan")
    lessons = relationship("Lesson", back_populates="subject", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="subject", cascade="all, delete-orphan")


class GradeSection(Base, TimestampSoftDeleteMixin):
    __tablename__ = "grade_sections"
    __table_args__ = (
        UniqueConstraint("grade_level", "name", name="uq_grade_section_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    grade_level = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    groups = relationship("SectionGroup", back_populates="section", cascade="all, delete-orphan")


class SectionGroup(Base, TimestampSoftDeleteMixin):
    __tablename__ = "section_groups"
    __table_args__ = (
        UniqueConstraint("section_id", "name", name="uq_section_group_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("grade_sections.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    section = relationship("GradeSection", back_populates="groups")


class TeacherCode(Base, TimestampSoftDeleteMixin):
    __tablename__ = "teacher_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    is_used = Column(Boolean, default=False)
    used_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # العلاقات
    subject = relationship("Subject", back_populates="teacher_codes")
    used_by = relationship("User", foreign_keys=[used_by_id])


class Enrollment(Base, TimestampSoftDeleteMixin):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="uq_student_subject_enrollment"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    enrolled_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    progress = Column(Float, default=0.0, nullable=False)
    completion_rate = Column(Float, default=0.0, nullable=False)
    grade = Column(Float, nullable=True)
    attendance_percentage = Column(Float, default=0.0, nullable=False)
    status = Column(String, default="active", nullable=False, index=True)

    # العلاقات
    student = relationship("User", back_populates="enrollments", foreign_keys=[student_id])
    subject = relationship("Subject", back_populates="enrollments")


class Lecture(Base, TimestampSoftDeleteMixin):
    __tablename__ = "lectures"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    meeting_url = Column(String, nullable=True)
    meeting_platform = Column(String, nullable=True)
    recording_url = Column(String, nullable=True)
    attachments = Column(Text, nullable=True)
    lecture_status = Column(String, default="scheduled", nullable=False, index=True)

    # العلاقات
    subject = relationship("Subject", back_populates="lectures")
    attendances = relationship("LectureAttendance", back_populates="lecture", cascade="all, delete-orphan")


class Homework(Base, TimestampSoftDeleteMixin):
    __tablename__ = "homeworks"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    file_url = Column(String, nullable=True)  # ملف مرفق من المدرس
    deadline = Column(DateTime(timezone=True), nullable=False)

    # العلاقات
    subject = relationship("Subject", back_populates="homeworks")
    submissions = relationship("Submission", back_populates="homework", cascade="all, delete-orphan")


class Submission(Base, TimestampSoftDeleteMixin):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    homework_id = Column(Integer, ForeignKey("homeworks.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    file_url = Column(String, nullable=False)  # ملف إجابة الطالب
    submitted_at = Column(DateTime(timezone=True), default=now_utc)
    grade = Column(Float, nullable=True)
    teacher_notes = Column(Text, nullable=True)
    status = Column(String, default="submitted")  # 'submitted', 'completed', 'late'

    # العلاقات
    homework = relationship("Homework", back_populates="submissions")
    student = relationship("User", back_populates="submissions", foreign_keys=[student_id])


class Rating(Base, TimestampSoftDeleteMixin):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("student_id", "teacher_id", "subject_id", name="uq_rating_student_teacher_subject"),
        CheckConstraint("stars >= 1 AND stars <= 5", name="ck_rating_stars_range"),
    )

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    stars = Column(Integer, nullable=False)  # 1 to 5
    comment = Column(Text, nullable=True)

    # العلاقات
    teacher = relationship("User", foreign_keys=[teacher_id], back_populates="ratings_received")
    student = relationship("User", foreign_keys=[student_id], back_populates="ratings_given")
    subject = relationship("Subject", back_populates="ratings")


class Notification(Base, TimestampSoftDeleteMixin):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String, nullable=False)  # e.g., 'homework_deadline', 'homework_submitted', 'homework_graded', 'lecture_start', 'teacher_rated'
    is_read = Column(Boolean, default=False)

    # العلاقات
    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])


class PasswordReset(Base, TimestampSoftDeleteMixin):
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False)

    # العلاقات
    user = relationship("User", back_populates="password_resets", foreign_keys=[user_id])


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=True)


class SubjectPrerequisite(Base, TimestampSoftDeleteMixin):
    __tablename__ = "subject_prerequisites"
    __table_args__ = (
        UniqueConstraint("subject_id", "prerequisite_subject_id", name="uq_subject_prerequisite"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    prerequisite_subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)

    subject = relationship("Subject", foreign_keys=[subject_id], back_populates="prerequisites")
    prerequisite_subject = relationship("Subject", foreign_keys=[prerequisite_subject_id])


class LectureAttendance(Base, TimestampSoftDeleteMixin):
    __tablename__ = "lecture_attendance"
    __table_args__ = (
        UniqueConstraint("lecture_id", "student_id", name="uq_lecture_student_attendance"),
    )

    id = Column(Integer, primary_key=True, index=True)
    lecture_id = Column(Integer, ForeignKey("lectures.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="absent", index=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    left_at = Column(DateTime(timezone=True), nullable=True)

    lecture = relationship("Lecture", back_populates="attendances")
    student = relationship("User", foreign_keys=[student_id])


class TutorAvailability(Base, TimestampSoftDeleteMixin):
    __tablename__ = "tutor_availability"

    id = Column(Integer, primary_key=True, index=True)
    tutor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)
    is_booked = Column(Boolean, default=False, nullable=False, index=True)

    tutor = relationship("User", foreign_keys=[tutor_id])


class TutorBooking(Base, TimestampSoftDeleteMixin):
    __tablename__ = "tutor_bookings"

    id = Column(Integer, primary_key=True, index=True)
    tutor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    availability_id = Column(Integer, ForeignKey("tutor_availability.id"), nullable=True, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    meeting_url = Column(String, nullable=True)
    status = Column(String, default="pending", nullable=False, index=True)
    price = Column(Float, default=0.0, nullable=False)
    payment_status = Column(String, default="unpaid", nullable=False, index=True)

    tutor = relationship("User", foreign_keys=[tutor_id])
    student = relationship("User", foreign_keys=[student_id])
    availability = relationship("TutorAvailability", foreign_keys=[availability_id])


class TutorReview(Base, TimestampSoftDeleteMixin):
    __tablename__ = "tutor_reviews"
    __table_args__ = (
        UniqueConstraint("booking_id", "student_id", name="uq_tutor_review_booking_student"),
        CheckConstraint("stars >= 1 AND stars <= 5", name="ck_tutor_review_stars_range"),
    )

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("tutor_bookings.id"), nullable=False, index=True)
    tutor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    stars = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)


class WalletTransaction(Base, TimestampSoftDeleteMixin):
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("tutor_bookings.id"), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False, index=True)
    status = Column(String, default="pending", nullable=False, index=True)
    reference = Column(String, nullable=True, index=True)
    payment_method = Column(String, nullable=True, index=True)
    payer_phone = Column(String, nullable=True, index=True)
    provider_payload = Column(Text, nullable=True)


class Lesson(Base, TimestampSoftDeleteMixin):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("subject_id", "order_index", name="uq_lesson_subject_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    video_url = Column(String, nullable=True)
    attachment_url = Column(String, nullable=True)
    order_index = Column(Integer, default=1, nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=True)
    is_published = Column(Boolean, default=False, nullable=False, index=True)

    subject = relationship("Subject", back_populates="lessons")
    quizzes = relationship("Quiz", back_populates="lesson", cascade="all, delete-orphan")


class Quiz(Base, TimestampSoftDeleteMixin):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    pass_score = Column(Float, default=60.0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False, index=True)

    subject = relationship("Subject", back_populates="quizzes")
    lesson = relationship("Lesson", back_populates="quizzes")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")
    attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base, TimestampSoftDeleteMixin):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    options = Column(Text, nullable=False)
    correct_answer = Column(String, nullable=False)
    explanation = Column(Text, nullable=True)
    points = Column(Float, default=1.0, nullable=False)

    quiz = relationship("Quiz", back_populates="questions")


class QuizAttempt(Base, TimestampSoftDeleteMixin):
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    answers = Column(Text, nullable=False)
    score = Column(Float, default=0.0, nullable=False)
    passed = Column(Boolean, default=False, nullable=False, index=True)

    quiz = relationship("Quiz", back_populates="attempts")
    student = relationship("User", foreign_keys=[student_id])


class Certificate(Base, TimestampSoftDeleteMixin):
    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="uq_certificate_student_subject"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    verification_code = Column(String, unique=True, nullable=False, index=True)
    final_score = Column(Float, default=0.0, nullable=False)
    issued_at = Column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    refresh_token_hash = Column(String, unique=True, nullable=False, index=True)
    ip_address = Column(String, nullable=True)
    browser = Column(String, nullable=True)
    device_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_activity = Column(DateTime(timezone=True), default=now_utc)
    is_revoked = Column(Boolean, default=False, nullable=False, index=True)

    user = relationship("User", back_populates="sessions")


class UserActivity(Base):
    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)

    user = relationship("User", back_populates="activities")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=True)
    target_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)
