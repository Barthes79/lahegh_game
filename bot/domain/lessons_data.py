"""
دروس و آزمون‌های «مسیر انتظار» (بخش نماز ← دروس).

این فایل منبع حقیقت محتوای آموزشی است؛ منطق آزمون (نمره‌دهی و قبولی) هم اینجا و بدون دیتابیس است
تا مستقیم تست شود.

برای پر کردن محتوا بعداً:
  - فایل درس: به LESSONS[i].media یک LessonMedia اضافه کن؛ یا با file_id تلگرام
    (LessonMedia("audio", file_id="...")) یا با مسیر فایل نسبت به ریشه‌ی پروژه
    (LessonMedia("pdf", path="bot/assets/lessons/x.pdf")). kind یکی از audio | video | pdf است.
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
# بعد از باز کردن درس، دکمه‌ی «شنیدم» تا این مدت قابل کلیک نیست؛ بعد از «شنیدم» دکمه‌ی آزمون می‌آید.
LISTEN_WAIT_SECONDS = 60

# درسی که قبولی در آزمونش شرط رفتن از سطح ۱ به سطح ۲ است.
LEVEL_1_REQUIRED_LESSON = 1
# درسی که قبولی در آزمونش شرط رفتن از سطح ۲ به سطح ۳ است.
LEVEL_2_REQUIRED_LESSON = 2
# درس ۲ فقط برای کسی که به سطح ۲ رسیده باز می‌شود.
LESSON_MIN_LEVEL: dict[int, int] = {2: 2}
# درس‌هایی که قبل از آزمون باید «شنیدم» زده شود.
LISTEN_REQUIRED_LESSONS = frozenset({1, 2})


@dataclass(frozen=True)
class LessonMedia:
    kind: str  # "audio" | "video" | "pdf"
    path: str = ""  # مسیر فایل (نسبت به ریشه‌ی پروژه) — اگر file_id نباشد
    caption: str = ""
    file_id: str = ""  # file_id تلگرام (اولویت با این است)


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
    # حداقل پاسخ درست برای قبولی (None = EXAM_PASS_SCORE پیش‌فرض)
    pass_score_override: int | None = None

    @property
    def question_count(self) -> int:
        return len(self.questions)

    @property
    def pass_score(self) -> int:
        if self.pass_score_override is not None:
            return self.pass_score_override
        return min(EXAM_PASS_SCORE, self.question_count)


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa(n: int) -> str:
    return str(n).translate(_FA_DIGITS)


def _lesson1_questions() -> tuple[Question, ...]:
    """سؤال‌های آزمون درس ۱ (گزینه‌ها به همین ترتیب نمایش داده می‌شوند؛ ترتیب سؤال‌ها تصادفی است)."""
    raw = [
        (
            "در آیات و روایات کدام یک از تعبیر های زیر برای نماز به کار برده نشده است؟",
            ("صورت دین", "اساس دین", "ستون دین", "اصول دین"),
            3,
        ),
        (
            "پیامبر اکرم ص برای کسی که نماز اول وقت بخواند چه چیزی را ضمانت میکنند؟ (۱ مورد صحیح)",
            ("آسایش و راحتی در زندگی", "برطرف شدن غم و غصه", "بالاترین درجه بهشت", "ارتباط با عالم غیب"),
            1,
        ),
        (
            "نماز برای از بین رفتن غم از کدام معصوم توصیه شده؟",
            ("امام علی (ع)", "امام رضا (ع)", "امام صادق (ع)", "رسول اکرم(ص)"),
            1,
        ),
        (
            "کدام مورد از اعمال مستحب قبل نماز نمیباشد؟",
            ("وضو گرفتن", "مسواک زدن", "اذان گفتن", "عطر زدن"),
            0,
        ),
        (
            "پیامبر ص فرمودند هر کاری که بر نماز مقدم شود ......... است.",
            ("حرام", "مستحب", "مکروه", "ابتر"),
            3,
        ),
        (
            "به ترتیب در رکعت اول و دومِ نمازی که امام رضا (ع) برای از بین رفتن غم توصیه کردند چه سوره هایی خوانده میشود؟",
            (
                "حمد و قدر، حمد و آیت الکرسی",
                "حمد و آیت‌الکرسی، حمد و قدر",
                "حمد و آیت الکرسی، حمد و توحید",
                "حمد و توحید، حمد و آیت الکرسی",
            ),
            1,
        ),
        (
            "خداوند در قرآن فرموده است: از روزه و نماز کمک بگیرید. واژه عربی که در این آیه به روزه اشاره میکند کدام است؟!",
            ("صوم", "صلاه", "صبر", "صمت"),
            2,
        ),
    ]
    return tuple(
        Question(id=i, text=text, options=options, correct=correct)
        for i, (text, options, correct) in enumerate(raw, start=1)
    )


def _lesson2_test_questions() -> tuple[Question, ...]:
    """۱۰ سؤال نمونه‌ی درس ۲ فقط برای تست جریان؛ بعداً با سؤال‌های اصلی جایگزین می‌شود."""
    raw = [
        ("ذکر اصلی بازی کدام است؟", ("سبحان الله", "اللهم عجل لولیک الفرج", "الحمدلله", "الله اکبر"), 1),
        ("امام دوازدهم شیعیان کیست؟", ("امام حسین (ع)", "امام رضا (ع)", "امام مهدی (عج)", "امام جواد (ع)"), 2),
        ("پیامبر خاتم کیست؟", ("حضرت عیسی (ع)", "حضرت محمد (ص)", "حضرت موسی (ع)", "حضرت ابراهیم (ع)"), 1),
        ("قرآن چند سوره دارد؟", ("۱۱۰", "۱۱۴", "۱۲۰", "۱۰۰"), 1),
        ("اولین سوره‌ی قرآن کدام است؟", ("بقره", "ناس", "حمد", "یس"), 2),
        ("ماه روزه‌داری مسلمانان کدام است؟", ("رجب", "شعبان", "محرم", "رمضان"), 3),
        ("روز جمعه با خواندن کدام دعا آشناتر است؟", ("دعای ندبه", "دعای کمیل", "دعای عرفه", "دعای جوشن"), 0),
        ("در شبانه‌روز چند نماز واجب داریم؟", ("۳ نماز", "۴ نماز", "۵ نماز", "۶ نماز"), 2),
        ("قبله‌ی مسلمانان کجاست؟", ("مسجدالاقصی", "کعبه", "مسجد کوفه", "مسجد النبی"), 1),
        ("با گفتن چه چیزی نماز را شروع می‌کنیم؟", ("بسم الله", "سبحان الله", "الله اکبر", "سلام"), 2),
    ]
    assert len(raw) == EXAM_QUESTION_COUNT
    return tuple(
        Question(id=i, text=text, options=options, correct=correct)
        for i, (text, options, correct) in enumerate(raw, start=1)
    )


# file_id فایل صوتی درس ۱ (آپلودشده با همین ربات)
LESSON_1_AUDIO_FILE_ID = "CQACAgQAAxkBAAICbmrBuIOwFtob9iqqh8lqsgk1mbDEAAJsIQACv8AwUpjyz0eYRypkPQQ"


LESSONS: tuple[Lesson, ...] = (
    Lesson(
        number=1,
        title="درس ۱: نماز",
        available=True,
        intro="🎧 فایل صوتی درس برات فرستاده می‌شه؛ بهش گوش بده.",
        media=(LessonMedia("audio", file_id=LESSON_1_AUDIO_FILE_ID, caption="🎧 درس ۱: نماز"),),
        questions=_lesson1_questions(),
        pass_score_override=6,  # ۶ از ۷ (حدود ۸۰٪)
    ),
    Lesson(
        number=2,
        title="درس ۲",
        available=True,
        intro="🎧 فایل صوتی درس زیر همین پیام هست؛ بهش گوش بده. با قبولی در آزمونش وارد سطح ۳ می‌شی.",
        questions=_lesson2_test_questions(),
    ),
    *(Lesson(number=n, title=f"درس {_fa(n)}") for n in range(3, LESSON_COUNT + 1)),
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
        passed=correct_count >= lesson.pass_score,
    )
