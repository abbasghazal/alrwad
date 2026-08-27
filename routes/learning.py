import json
import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db
from services.audit import write_audit_log
from services.notifications import create_notification
from utils import PaginatedResponse, PaginationParams, paginate_query


router = APIRouter(prefix="/learning", tags=["المحتوى التعليمي والاختبارات"])


def teacher_can_manage_subject(db: Session, teacher: models.User, subject_id: int) -> bool:
    if teacher.role != "teacher":
        return False
    if teacher.subject_id == subject_id:
        return True
    return db.query(models.TeacherSubject).filter(
        models.TeacherSubject.teacher_id == teacher.id,
        models.TeacherSubject.subject_id == subject_id,
        models.TeacherSubject.is_deleted == False,
    ).first() is not None


def ensure_subject_access(db: Session, user: models.User, subject_id: int, manage: bool = False) -> None:
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.is_deleted == False).first()
    if not subject:
        raise HTTPException(status_code=404, detail="المادة غير موجودة")
    if user.role == "owner":
        return
    if manage:
        if not teacher_can_manage_subject(db, user, subject_id):
            raise HTTPException(status_code=403, detail="لا تملك صلاحية إدارة محتوى هذه المادة")
        return
    if user.role == "teacher" and teacher_can_manage_subject(db, user, subject_id):
        return
    enrolled = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == user.id,
        models.Enrollment.subject_id == subject_id,
        models.Enrollment.status == "active",
        models.Enrollment.is_deleted == False,
    ).first()
    if not enrolled:
        raise HTTPException(status_code=403, detail="يجب التسجيل في المادة للوصول لهذا المحتوى")


def serialize_question(row: models.QuizQuestion, include_answer: bool = False) -> dict:
    payload = {
        "id": row.id,
        "quiz_id": row.quiz_id,
        "prompt": row.prompt,
        "options": json.loads(row.options),
        "explanation": row.explanation,
        "points": row.points,
    }
    if include_answer:
        payload["correct_answer"] = row.correct_answer
    return payload


@router.get("/subjects/{subject_id}/lessons", response_model=PaginatedResponse)
def get_lessons(
    subject_id: int,
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ensure_subject_access(db, current_user, subject_id)
    query = db.query(models.Lesson).filter(
        models.Lesson.subject_id == subject_id,
        models.Lesson.is_deleted == False,
    )
    if current_user.role == "student":
        query = query.filter(models.Lesson.is_published == True)
    return paginate_query(query.order_by(models.Lesson.order_index.asc()), pagination)


@router.post("/subjects/{subject_id}/lessons", response_model=schemas.LessonResponse)
def create_lesson(
    subject_id: int,
    payload: schemas.LessonCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ensure_subject_access(db, current_user, subject_id, manage=True)
    lesson = models.Lesson(
        subject_id=subject_id,
        title=payload.title.strip(),
        content=payload.content,
        video_url=payload.video_url,
        attachment_url=payload.attachment_url,
        order_index=payload.order_index,
        duration_minutes=payload.duration_minutes,
        is_published=payload.is_published,
    )
    db.add(lesson)
    write_audit_log(db, action="create_lesson", actor_id=current_user.id, target_type="subject", target_id=subject_id)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.post("/subjects/{subject_id}/quizzes", response_model=schemas.QuizResponse)
def create_quiz(
    subject_id: int,
    payload: schemas.QuizCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ensure_subject_access(db, current_user, subject_id, manage=True)
    if payload.lesson_id:
        lesson = db.query(models.Lesson).filter(
            models.Lesson.id == payload.lesson_id,
            models.Lesson.subject_id == subject_id,
            models.Lesson.is_deleted == False,
        ).first()
        if not lesson:
            raise HTTPException(status_code=404, detail="الدرس غير موجود داخل هذه المادة")
    quiz = models.Quiz(
        subject_id=subject_id,
        lesson_id=payload.lesson_id,
        title=payload.title.strip(),
        description=payload.description,
        pass_score=payload.pass_score,
        max_attempts=payload.max_attempts,
        is_published=payload.is_published,
    )
    db.add(quiz)
    write_audit_log(db, action="create_quiz", actor_id=current_user.id, target_type="subject", target_id=subject_id)
    db.commit()
    db.refresh(quiz)
    return quiz


@router.get("/subjects/{subject_id}/quizzes", response_model=PaginatedResponse)
def get_quizzes(
    subject_id: int,
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ensure_subject_access(db, current_user, subject_id)
    query = db.query(models.Quiz).filter(models.Quiz.subject_id == subject_id, models.Quiz.is_deleted == False)
    if current_user.role == "student":
        query = query.filter(models.Quiz.is_published == True)
    return paginate_query(query.order_by(models.Quiz.created_at.desc()), pagination)


@router.post("/quizzes/{quiz_id}/questions")
def add_quiz_question(
    quiz_id: int,
    payload: schemas.QuizQuestionCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id, models.Quiz.is_deleted == False).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="الاختبار غير موجود")
    ensure_subject_access(db, current_user, quiz.subject_id, manage=True)
    if payload.correct_answer not in payload.options:
        raise HTTPException(status_code=400, detail="الإجابة الصحيحة يجب أن تكون ضمن الخيارات")
    question = models.QuizQuestion(
        quiz_id=quiz_id,
        prompt=payload.prompt,
        options=json.dumps(payload.options, ensure_ascii=False),
        correct_answer=payload.correct_answer,
        explanation=payload.explanation,
        points=payload.points,
    )
    db.add(question)
    write_audit_log(db, action="add_quiz_question", actor_id=current_user.id, target_type="quiz", target_id=quiz_id)
    db.commit()
    return {"message": "تمت إضافة السؤال", "id": question.id}


@router.get("/quizzes/{quiz_id}/questions")
def get_quiz_questions(
    quiz_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id, models.Quiz.is_deleted == False).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="الاختبار غير موجود")
    ensure_subject_access(db, current_user, quiz.subject_id)
    if current_user.role == "student" and not quiz.is_published:
        raise HTTPException(status_code=403, detail="الاختبار غير منشور")
    include_answer = current_user.role in {"owner", "teacher"}
    return [serialize_question(row, include_answer=include_answer) for row in quiz.questions if not row.is_deleted]


@router.post("/quizzes/{quiz_id}/submit")
def submit_quiz(
    quiz_id: int,
    payload: schemas.QuizSubmit,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db),
):
    quiz = db.query(models.Quiz).filter(
        models.Quiz.id == quiz_id,
        models.Quiz.is_published == True,
        models.Quiz.is_deleted == False,
    ).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="الاختبار غير متاح")
    ensure_subject_access(db, current_student, quiz.subject_id)

    attempts_count = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.quiz_id == quiz_id,
        models.QuizAttempt.student_id == current_student.id,
        models.QuizAttempt.is_deleted == False,
    ).count()
    if attempts_count >= quiz.max_attempts:
        raise HTTPException(status_code=400, detail="تم استنفاد عدد المحاولات")

    questions: List[models.QuizQuestion] = [q for q in quiz.questions if not q.is_deleted]
    if not questions:
        raise HTTPException(status_code=400, detail="لا يحتوي الاختبار على أسئلة")
    earned = 0.0
    total = sum(float(q.points or 0) for q in questions)
    for question in questions:
        answer = payload.answers.get(str(question.id))
        if answer == question.correct_answer:
            earned += float(question.points or 0)
    score = round((earned / total) * 100, 2) if total else 0.0
    passed = score >= quiz.pass_score
    attempt = models.QuizAttempt(
        quiz_id=quiz_id,
        student_id=current_student.id,
        answers=json.dumps(payload.answers, ensure_ascii=False),
        score=score,
        passed=passed,
    )
    db.add(attempt)
    create_notification(db, current_student.id, "نتيجة اختبار", f"حصلت على {score}% في اختبار {quiz.title}", "quiz_result")
    db.commit()
    return {"score": score, "passed": passed, "attempt_id": attempt.id}


@router.post("/subjects/{subject_id}/certificate", response_model=schemas.CertificateResponse)
def issue_certificate(
    subject_id: int,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db),
):
    ensure_subject_access(db, current_student, subject_id)
    quizzes = db.query(models.Quiz).filter(
        models.Quiz.subject_id == subject_id,
        models.Quiz.is_published == True,
        models.Quiz.is_deleted == False,
    ).all()
    if not quizzes:
        raise HTTPException(status_code=400, detail="لا توجد اختبارات منشورة لإصدار شهادة")
    scores = []
    for quiz in quizzes:
        best = db.query(func.max(models.QuizAttempt.score)).filter(
            models.QuizAttempt.quiz_id == quiz.id,
            models.QuizAttempt.student_id == current_student.id,
            models.QuizAttempt.passed == True,
            models.QuizAttempt.is_deleted == False,
        ).scalar()
        if best is None:
            raise HTTPException(status_code=400, detail="يجب اجتياز جميع اختبارات المادة أولاً")
        scores.append(float(best))
    existing = db.query(models.Certificate).filter(
        models.Certificate.subject_id == subject_id,
        models.Certificate.student_id == current_student.id,
        models.Certificate.is_deleted == False,
    ).first()
    if existing:
        return existing
    certificate = models.Certificate(
        subject_id=subject_id,
        student_id=current_student.id,
        verification_code=secrets.token_urlsafe(12),
        final_score=round(sum(scores) / len(scores), 2),
    )
    db.add(certificate)
    create_notification(
        db,
        current_student.id,
        "تم إصدار شهادة",
        "تهانينا، تم إصدار شهادة إكمال المادة.",
        "certificate_issued",
        send_email=True,
    )
    write_audit_log(db, action="issue_certificate", actor_id=current_student.id, target_type="subject", target_id=subject_id)
    db.commit()
    db.refresh(certificate)
    return certificate


@router.get("/certificates/{verification_code}", response_model=schemas.CertificateResponse)
def verify_certificate(verification_code: str, db: Session = Depends(get_db)):
    certificate = db.query(models.Certificate).filter(
        models.Certificate.verification_code == verification_code,
        models.Certificate.is_deleted == False,
    ).first()
    if not certificate:
        raise HTTPException(status_code=404, detail="الشهادة غير موجودة")
    return certificate
