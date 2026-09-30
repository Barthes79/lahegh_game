"""
دروس و آزمون‌های «مسیر انتظار» (بخش نماز ← دروس).

این فایل منبع حقیقت محتوای آموزشی است؛ منطق آزمون (نمره‌دهی و قبولی) هم اینجا و بدون دیتابیس است
تا مستقیم تست شود.

برای پر کردن محتوا بعداً:
  - فایل درس: به LESSONS[i].media یک LessonMedia("audio"|"video"|"pdf", "مسیر/فایل") اضافه کن
    (مسیر نسبت به ریشه‌ی پروژه؛ فایل‌ها را داخل پوشه‌ی bot/assets/lessons/ بگذار).
  - سؤال‌ها: به‌جای _placeholder_questions() لیست Question واقعی بگذار. correct = شماره‌ی گزینه‌ی
    درست (از ۰). تعداد سؤال‌ها همان EXAM_QUESTION_COUNT است.
  - درس‌های بعدی: available=True کن (و برای آن‌ها سؤال بگذار).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

LESSON_COUNT = 10
EXAM_QUESTION_COUNT = 10
EXAM_PASS_SCORE = 8  # حداقل پاسخ درست برای قبولی
EXAM_RETRY_COOLDOWN_SECONDS = 15 * 60  # بعد از مردودی، ۱۵ دقیقه صبر

# درسی که قبولی در آزمونش شرط رفتن از سطح ۱ به سطح ۲ است.
LEVEL_1_REQUIRED_LESSON = 1


@dataclass(frozen=True)
class LessonMedia:
    kind: str  # "audio" | "video" | "pdf"
    path: str  # مسیر فایل (نسبت به ریشه‌ی پروژه)
    caption: str = ""


@dataclass(frozen=True)
class Question:
    id: int
    text: str
    options: tuple[str, ...]
    correct: int  # اندیس گزینه‌ی درست (از ۰)


@dataclass(frozen=True)
class Lesson:
    number: int
    title: str
    available: bool = False
    intro: str = ""  # متن توضیح درس (وقتی فایل نیست یا کنار فایل)
    media: tuple[LessonMedia, ...] = ()
    questions: tuple[Question, ...] = field(default_factory=tuple)


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa(n: int) -> str:
    return str(n).translate(_FA_DIGITS)


def _placeholder_questions() -> tuple[Question, ...]:
    """سؤال‌های نمونه فقط برای تست ساختار؛ جوابِ هر سؤال داخل خود متنش نوشته شده."""
    questions = []
    for i in range(1, EXAM_QUESTION_COUNT + 1):
        correct = (i - 1) % 4
        questions.append(
            Question(
                id=i,
                text=f"سؤال نمونه {i}: (برای تست) گزینه‌ی شماره‌ی {correct + 1} رو انتخاب کن.",
                options=tuple(f"گزینه {n}" for n in range(1, 5)),
                correct=correct,
            )
        )
    return tuple(questions)


LESSONS: tuple[Lesson, ...] = (
    Lesson(
        number=1,
        title="درس ۱: نماز",
        available=True,
        intro="محتوای این درس به‌زودی اضافه می‌شود.",
        questions=_placeholder_questions(),
    ),
    *(Lesson(number=n, title=f"درس {_fa(n)}") for n in range(2, LESSON_COUNT + 1)),
)
LESSON_BY_NUMBER: dict[int, Lesson] = {lesson.number: lesson for lesson in LESSONS}


def shuffled_question_ids(lesson: Lesson, rng: random.Random | None = None) -> list[int]:
    """ترتیب تصادفی شناسه‌ی سؤال‌ها برای یک دور آزمون (هر دور یک ترتیب جدید)."""
    ids = [q.id for q in lesson.questions]
    (rng or random).shuffle(ids)
    return ids


@dataclass(frozen=True)
class ExamGrade:
    total: int
    correct_count: int
    wrong_positions: tuple[int, ...]  # شماره‌ی سؤال‌های غلط به ترتیبی که کاربر دیده (از ۱)
    wrong_question_ids: tuple[int, ...]
    passed: bool

    @property
    def wrong_count(self) -> int:
        return self.total - self.correct_count


def grade_exam(lesson: Lesson, question_order: list[int], answers: list[int]) -> ExamGrade:
    """
    question_order: شناسه‌ی سؤال‌ها به ترتیب نمایش؛ answers: گزینه‌ی انتخابی کاربر برای هر کدام.
    سؤالی که بی‌پاسخ مانده غلط حساب می‌شود.
    """
    by_id = {q.id: q for q in lesson.questions}
    wrong_positions: list[int] = []
    wrong_ids: list[int] = []
    correct_count = 0
    for position, qid in enumerate(question_order, start=1):
        question = by_id[qid]
        chosen = answers[position - 1] if position - 1 < len(answers) else None
        if chosen == question.correct:
            correct_count += 1
        else:
            wrong_positions.append(position)
            wrong_ids.append(qid)
    return ExamGrade(
        total=len(question_order),
        correct_count=correct_count,
        wrong_positions=tuple(wrong_positions),
        wrong_question_ids=tuple(wrong_ids),
        passed=correct_count >= EXAM_PASS_SCORE,
    )
