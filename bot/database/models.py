"""
مدل‌های ORM. Schema واقعی جداول توسط فایل‌های SQL داخل bot/database/migrations
ساخته می‌شود (منبع حقیقت schema همان‌جاست)؛ این مدل‌ها باید همیشه با آخرین migration هماهنگ باشند.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    game_started: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    game_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    active_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    noor_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    noor_total_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    salawat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dhikr_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_activities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_activity_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_salawat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_dhikr_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_dhikr_cooldown_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # کولداون مستقل ذکرهای ویژه‌ی «حلقه ذکر» (istighfar_long و بقیه‌ی ۵ ذکر)؛ کاملاً
    # جدا از last_dhikr_at است تا مقدار CIRCLE_DHIKR_COOLDOWN_SECONDS تأثیری روی
    # کولداون ذکرهای عادی (لا اله الا الله و...) نداشته باشد و برعکس.
    last_circle_dhikr_at: Mapped[datetime | None] = mapped_column(nullable=True)

    reaction_explained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    bank_azkar_unlocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nameh_amal_unlocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tasbih_unlocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tasbih_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    chest_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_chest_explained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_chest_created_at: Mapped[datetime | None] = mapped_column(nullable=True)

    last_reminder_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # --- Level 2: صف دعا (التماس دعا) ---
    # شمارنده‌ی روزانه‌ی ذکر رایگان معتبر (صلوات حساب نمی‌شود)؛ شرط باز شدن صف برای همان روز.
    # مبنای روز Asia/Tehran است (bot/domain/dua_queue.py). daily_free_dhikr_date به‌صورت
    # رشته‌ی YYYY-MM-DD ذخیره می‌شود؛ اگر با «امروز» فرق داشت، شمارنده باید صفر در نظر گرفته شود.
    daily_free_dhikr_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_free_dhikr_date: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Level 2: حلقه ذکر ---
    # هر کاربر فقط می‌تواند عضو *یک* حلقه‌ی فعال باشد؛ این فیلد منبع اصلی حقیقت برای
    # «کاربر الان عضو کدام حلقه است» است (NULL یعنی در هیچ حلقه‌ای نیست).
    active_circle_id: Mapped[int | None] = mapped_column(
        ForeignKey("dhikr_circles.id"), nullable=True
    )
    circle_personal_reward_date: Mapped[str | None] = mapped_column(String, nullable=True)

    # ذکر تصادفی نمایشی هنگام نوشتن «حلقه ذکر»؛ برای هر کاربر تا ۲۴ ساعت ثابت می‌ماند.
    circle_display_dhikr_key: Mapped[str | None] = mapped_column(String, nullable=True)
    circle_display_dhikr_assigned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # سهم حلقه در یک پنجره‌ی ۲۴ ساعته که از اولین ذکر حلقه‌ی خود کاربر شروع می‌شود.
    circle_daily_dhikr_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circle_daily_dhikr_started_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # --- Level 3: مشاغل ---
    # job_key کلید شغل انتخاب‌شده (bot/domain/jobs_data.py)؛ NULL یعنی هنوز شغلی انتخاب نشده.
    # tool_level سطح ابزار شغل (۱ تا ۵)؛ toman موجودی تومانی برای خرید از مارکت.
    job_key: Mapped[str | None] = mapped_column(String, nullable=True)
    job_selected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    tool_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    toman: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dhikr_unlocks: Mapped[list["DhikrUnlock"]] = relationship(back_populates="user")
    chests: Mapped[list["Chest"]] = relationship(back_populates="user")
    dua_queues: Mapped[list["DuaQueue"]] = relationship(
        back_populates="owner", foreign_keys="DuaQueue.owner_user_id"
    )
    dua_queue_answers: Mapped[list["DuaQueueAnswer"]] = relationship(
        back_populates="responder", foreign_keys="DuaQueueAnswer.responder_user_id"
    )


class DhikrUnlock(Base):
    __tablename__ = "dhikr_unlocks"
    __table_args__ = (UniqueConstraint("user_id", "dhikr_key", name="uq_dhikr_unlocks_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    dhikr_key: Mapped[str] = mapped_column(String, nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(nullable=False)

    user: Mapped["User"] = relationship(back_populates="dhikr_unlocks")


class Chest(Base):
    __tablename__ = "chests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    opened: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opened_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reward_noor: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship(back_populates="chests")


class DuaQueue(Base):
    """
    یک «صف دعا» که یک کاربر در گروه ساخته (Level 2).

    answers_count برای جلوگیری از COUNT مکرر روی dua_queue_answers نگه‌داری می‌شود
    و هر بار که یک پاسخ معتبر ثبت می‌شود، هم‌زمان با insert همان پاسخ افزایش می‌یابد.
    """

    __tablename__ = "dua_queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    answers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    closed_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # ذکر تصادفی این پنل (کلید در DUA_QUEUE_DHIKR_BY_KEY)؛ برای پنل‌های قدیمی NULL است.
    dhikr_key: Mapped[str | None] = mapped_column(String, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="dua_queues", foreign_keys=[owner_user_id])
    answers: Mapped[list["DuaQueueAnswer"]] = relationship(back_populates="queue")


class DuaQueueAnswer(Base):
    """
    یک پاسخ معتبر به یک صف دعا. هر کاربر فقط یک‌بار می‌تواند به یک صف پاسخ دهد
    (UNIQUE(queue_id, responder_user_id) در migration اعمال شده است).
    """

    __tablename__ = "dua_queue_answers"
    __table_args__ = (
        UniqueConstraint("queue_id", "responder_user_id", name="uq_dua_queue_answers_queue_responder"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("dua_queues.id"), nullable=False)
    responder_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    queue: Mapped["DuaQueue"] = relationship(back_populates="answers")
    responder: Mapped["User"] = relationship(
        back_populates="dua_queue_answers", foreign_keys=[responder_user_id]
    )


class DuaQueueExtraMessage(Base):
    """پیام وضعیتِ اضافه‌ای که برای یک پنل باز فرستاده شده؛ ریپلای روی آن هم پاسخ به پنل است."""

    __tablename__ = "dua_queue_extra_messages"
    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_dua_queue_extra_chat_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("dua_queues.id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class DhikrCircle(Base):
    """
    یک «حلقه ذکر» (Level 2). به هیچ تعداد عضوی محدود نیست؛ ۵ نفر فقط شرط milestone
    روزانه است، نه شرط ساخت/فعال بودن حلقه.

    milestone_paid_date: تاریخ (Asia/Tehran، رشته‌ی YYYY-MM-DD) آخرین روزی که milestone
    پنج‌نفره برای این حلقه پرداخت شده؛ NULL یعنی هنوز هیچ‌وقت. برای جلوگیری از پرداخت
    دوباره‌ی همان روز چک می‌شود.
    """

    __tablename__ = "dhikr_circles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    creator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    milestone_paid_date: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="حلقه ذکر")
    group_bonus_blocked_date: Mapped[str | None] = mapped_column(String, nullable=True)
    # چرخه‌ی ۲۴ ساعته‌ی خود حلقه از اولین ذکر معتبر هر عضو شروع می‌شود.
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    creator: Mapped["User"] = relationship(foreign_keys=[creator_user_id])
    members: Mapped[list["DhikrCircleMember"]] = relationship(back_populates="circle")


class DhikrCircleMember(Base):
    """
    یک «عضویت» در یک حلقه (یک stint). اگر کاربر خارج شود و دوباره به همین یا حلقه‌ی
    دیگری بپیوندد، یک ردیف *جدید* ساخته می‌شود (سهم روزانه و ۷۲ ساعت از صفر شروع می‌شود)
    — ردیف‌های قدیمی status='left' برای تاریخچه باقی می‌مانند.

    daily_count/daily_date: سهم روزانه‌ی این عضو در این حلقه (مبنای روز Asia/Tehran).
    daily_completed_at: وقتی همین امروز به ۱۰/۱۰ رسیده (برای تعیین ۵ نفر «زودتر تکمیل‌کننده»
    برای milestone)؛ هر روز با تغییر daily_date دوباره NULL می‌شود.
    """

    __tablename__ = "dhikr_circle_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    circle_id: Mapped[int] = mapped_column(ForeignKey("dhikr_circles.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    left_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    daily_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_date: Mapped[str | None] = mapped_column(String, nullable=True)
    daily_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    panel_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    panel_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    circle: Mapped["DhikrCircle"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class UserRawMaterial(Base):
    """موجودی مواد اولیه‌ی یک کاربر برای یک محصول (Level 3)."""

    __tablename__ = "user_raw_materials"
    __table_args__ = (UniqueConstraint("user_id", "product_key", name="uq_user_raw_user_product"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_key: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UserProduction(Base):
    """تولید در جریان یک کاربر؛ با UNIQUE(user_id) فقط یک تولید هم‌زمان مجاز است (Level 3)."""

    __tablename__ = "user_productions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    product_key: Mapped[str] = mapped_column(String, nullable=False)
    dhikr_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dhikr_required: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(nullable=False)


class UserProduct(Base):
    """انبار محصولات تولیدشده: تعداد به‌ازای (محصول، ستاره) (Level 3)."""

    __tablename__ = "user_products"
    __table_args__ = (
        UniqueConstraint("user_id", "product_key", "stars", name="uq_user_products_user_key_stars"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_key: Mapped[str] = mapped_column(String, nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProcessedUpdate(Base):
    """
    برای جلوگیری از پردازش دوباره‌ی یک update تلگرام (retry، double click و ...).
    بخش ۲۰ سند: هر reward باید دقیقاً یک‌بار اعمال شود.
    """

    __tablename__ = "processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(nullable=False)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(nullable=False)
