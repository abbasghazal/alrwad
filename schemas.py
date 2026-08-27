from pydantic import BaseModel, EmailStr, Field
from typing import Dict, Optional, List
from datetime import datetime

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


# --- User Schemas ---
class UserBase(BaseModel):
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    role: str


class UserCreate(UserBase):
    password: str
    grade_level: Optional[str] = None
    section_id: Optional[int] = None
    group_id: Optional[int] = None
    subject_id: Optional[int] = None
    specialty: Optional[str] = None
    hourly_rate: Optional[float] = None
    teacher_code: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None


class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: Optional[str] = None


class UserResponse(UserBase):
    id: int
    grade_level: Optional[str] = None
    section_id: Optional[int] = None
    group_id: Optional[int] = None
    subject_id: Optional[int] = None
    specialty: Optional[str] = None
    hourly_rate: Optional[float] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    is_blocked: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Subject Schemas ---
class SubjectBase(BaseModel):
    name: str
    grade_level: str
    description: Optional[str] = None
    category: Optional[str] = None
    grade: Optional[str] = None
    semester: Optional[str] = None
    thumbnail: Optional[str] = None
    max_students: Optional[int] = None


class SubjectCreate(SubjectBase):
    pass


class SubjectResponse(SubjectBase):
    id: int
    is_archived: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- TeacherCode Schemas ---
class TeacherCodeCreate(BaseModel):
    subject_id: int
    expires_in_days: int = 7


class TeacherCodeResponse(BaseModel):
    id: int
    code: str
    subject_id: int
    is_used: bool
    used_by_id: Optional[int] = None
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# --- Lecture Schemas ---
class LectureBase(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    meeting_url: Optional[str] = None
    meeting_platform: Optional[str] = None
    recording_url: Optional[str] = None
    attachments: Optional[str] = None
    lecture_status: Optional[str] = "scheduled"


class LectureCreate(LectureBase):
    subject_id: Optional[int] = None


class LectureResponse(LectureBase):
    id: int
    subject_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Homework Schemas ---
class HomeworkBase(BaseModel):
    title: str
    description: str
    deadline: datetime


class HomeworkCreate(HomeworkBase):
    pass


class HomeworkResponse(HomeworkBase):
    id: int
    subject_id: int
    file_url: Optional[str] = None
    deadline: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# --- Submission Schemas ---
class SubmissionGrade(BaseModel):
    grade: float
    teacher_notes: Optional[str] = None


class SubmissionResponse(BaseModel):
    id: int
    homework_id: int
    student_id: int
    file_url: str
    submitted_at: datetime
    grade: Optional[float] = None
    teacher_notes: Optional[str] = None
    status: str
    student: Optional[UserResponse] = None

    class Config:
        from_attributes = True


# --- Rating Schemas ---
class RatingCreate(BaseModel):
    teacher_id: int
    stars: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class RatingResponse(BaseModel):
    id: int
    teacher_id: int
    student_id: int
    subject_id: int
    stars: int
    comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- Notification Schemas ---
class NotificationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Password Reset Schemas ---
class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetCodeVerify(BaseModel):
    email: EmailStr
    code: str


class PasswordResetVerify(PasswordResetCodeVerify):
    new_password: str
    new_password_confirm: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class EmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str


class UserStatusUpdate(BaseModel):
    user_id: int
    is_blocked: Optional[bool] = None
    role: Optional[str] = None
    permissions: Optional[str] = None


class SubjectPrerequisiteCreate(BaseModel):
    prerequisite_subject_id: int


class GradeSectionCreate(BaseModel):
    grade_level: str
    name: str
    description: Optional[str] = None


class GradeSectionResponse(BaseModel):
    id: int
    grade_level: str
    name: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SectionGroupCreate(BaseModel):
    section_id: int
    name: str
    description: Optional[str] = None


class SectionGroupResponse(BaseModel):
    id: int
    section_id: int
    name: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AttendanceUpdate(BaseModel):
    student_id: int
    status: str = Field(..., pattern="^(present|absent|late)$")
    joined_at: Optional[datetime] = None
    left_at: Optional[datetime] = None


class TutorAvailabilityCreate(BaseModel):
    start_time: datetime
    end_time: datetime


class TutorBookingCreate(BaseModel):
    tutor_id: int
    availability_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class TutorReviewCreate(BaseModel):
    booking_id: int
    stars: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class ManualPaymentCreate(BaseModel):
    booking_id: int
    amount: float = Field(..., gt=0)
    reference: str = Field(..., min_length=3, max_length=120)


class PaymentDecision(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    note: Optional[str] = None


class LessonCreate(BaseModel):
    title: str
    content: Optional[str] = None
    video_url: Optional[str] = None
    attachment_url: Optional[str] = None
    order_index: int = Field(1, ge=1)
    duration_minutes: Optional[int] = Field(None, ge=1)
    is_published: bool = False


class LessonResponse(LessonCreate):
    id: int
    subject_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class QuizCreate(BaseModel):
    title: str
    description: Optional[str] = None
    lesson_id: Optional[int] = None
    pass_score: float = Field(60, ge=0, le=100)
    max_attempts: int = Field(3, ge=1, le=20)
    is_published: bool = False


class QuizResponse(QuizCreate):
    id: int
    subject_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class QuizQuestionCreate(BaseModel):
    prompt: str
    options: List[str] = Field(..., min_length=2)
    correct_answer: str
    explanation: Optional[str] = None
    points: float = Field(1, gt=0)


class QuizQuestionResponse(BaseModel):
    id: int
    quiz_id: int
    prompt: str
    options: List[str]
    explanation: Optional[str] = None
    points: float


class QuizSubmit(BaseModel):
    answers: Dict[str, str]


class CertificateResponse(BaseModel):
    id: int
    student_id: int
    subject_id: int
    verification_code: str
    final_score: float
    issued_at: datetime

    class Config:
        from_attributes = True


class PaymentWebhookPayload(BaseModel):
    provider: str
    reference: str
    status: str = Field(..., pattern="^(approved|rejected|failed)$")
    amount: Optional[float] = None
    signature: Optional[str] = None


class IraqiPhonePaymentCreate(BaseModel):
    booking_id: int
    amount: float = Field(..., gt=0)
    payment_method: str = Field(..., pattern="^(zain_cash|asia_hawala|fastpay|qi_card|mastercard)$")
    payer_phone: str = Field(..., min_length=10, max_length=20)
    reference: Optional[str] = Field(None, min_length=3, max_length=120)


class BroadcastNotificationCreate(BaseModel):
    title: str
    message: str
    role: Optional[str] = None
    send_email: bool = False


class EmailTestRequest(BaseModel):
    to_email: Optional[EmailStr] = None


SMTPTestRequest = EmailTestRequest
