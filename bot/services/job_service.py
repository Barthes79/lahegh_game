"""
سرویس مشاغل Level 3: انتخاب شغل، ارتقای ابزار، خرید مواد اولیه از مارکت (تومان)،
شروع تولید، پیشرفت تولید با ذکر، و فروش محصولات.

همه‌ی توابع باید داخل یک تراکنش (session.begin()) صدا زده شوند؛ idempotency روی
update_id تلگرام را handler انجام می‌دهد (مثل پنل تسبیح).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User, UserProduct, UserProduction, UserRawMaterial
from bot.domain import jobs_data as jd


class JobResult:
    SUCCESS = "success"
    LEVEL_TOO_LOW = "level_too_low"
    ALREADY_HAS_JOB = "already_has_job"
    NO_JOB = "no_job"
    INVALID = "invalid"
    INSUFFICIENT_NOOR = "insufficient_noor"
    INSUFFICIENT_TOMAN = "insufficient_toman"
    NO_RAW_MATERIAL = "no_raw_material"
    PRODUCT_LOCKED = "product_locked"
    ALREADY_PRODUCING = "already_producing"
    MAX_TOOL_FOR_LEVEL = "max_tool_for_level"


@dataclass
class JobOutcome:
    result: str
    detail: int = 0  # مقدار کمکی (مثلاً سطح جدید ابزار / مبلغ / کمبود)


@dataclass
class ProductionProgress:
    """نتیجه‌ی اعمال یک ذکر روی تولید فعال (برای نمایش در گروه/PV)."""

    product_key: str
    done: int
    required: int
    completed: bool = False
    # فقط وقتی completed: {stars: quantity}
    produced: dict[int, int] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# خواندن وضعیت
# ---------------------------------------------------------------------------


async def get_raw_stock(session: AsyncSession, user: User) -> dict[str, int]:
    rows = await session.execute(select(UserRawMaterial).where(UserRawMaterial.user_id == user.id))
    return {r.product_key: r.quantity for r in rows.scalars() if r.quantity > 0}


async def get_inventory(session: AsyncSession, user: User) -> list[UserProduct]:
    rows = await session.execute(
        select(UserProduct)
        .where(UserProduct.user_id == user.id, UserProduct.quantity > 0)
        .order_by(UserProduct.product_key, UserProduct.stars)
    )
    return list(rows.scalars())


async def get_active_production(session: AsyncSession, user: User) -> UserProduction | None:
    row = await session.execute(select(UserProduction).where(UserProduction.user_id == user.id))
    return row.scalar_one_or_none()


# ---------------------------------------------------------------------------
# انتخاب شغل / ارتقای ابزار
# ---------------------------------------------------------------------------


async def choose_job(session: AsyncSession, user: User, job_key: str) -> JobOutcome:
    if user.level < jd.JOB_UNLOCK_LEVEL:
        return JobOutcome(JobResult.LEVEL_TOO_LOW)
    if user.job_key is not None:
        return JobOutcome(JobResult.ALREADY_HAS_JOB)
    if job_key not in jd.JOB_BY_KEY:
        return JobOutcome(JobResult.INVALID)
    if user.noor_current < jd.JOB_SELECT_COST_NOOR:
        return JobOutcome(JobResult.INSUFFICIENT_NOOR, jd.JOB_SELECT_COST_NOOR - user.noor_current)

    user.noor_current -= jd.JOB_SELECT_COST_NOOR  # noor_total_earned کم نمی‌شود
    user.job_key = job_key
    user.job_selected_at = _now()
    user.tool_level = jd.TOOL_START_LEVEL
    user.toman += jd.STARTING_TOMAN
    await session.flush()
    return JobOutcome(JobResult.SUCCESS)


async def upgrade_tool(session: AsyncSession, user: User) -> JobOutcome:
    if user.job_key is None:
        return JobOutcome(JobResult.NO_JOB)
    if user.tool_level >= jd.max_tool_level_for_user_level(user.level):
        return JobOutcome(JobResult.MAX_TOOL_FOR_LEVEL)
    cost = jd.get_tool_upgrade_cost(user.tool_level)
    if cost is None:
        return JobOutcome(JobResult.MAX_TOOL_FOR_LEVEL)
    if user.noor_current < cost:
        return JobOutcome(JobResult.INSUFFICIENT_NOOR, cost - user.noor_current)

    user.noor_current -= cost
    user.tool_level += 1
    await session.flush()
    return JobOutcome(JobResult.SUCCESS, user.tool_level)


# ---------------------------------------------------------------------------
# مارکت
# ---------------------------------------------------------------------------


def _product_for_user(user: User, product_key: str) -> tuple[jd.ProductDef | None, str | None]:
    """(product, error_result). محصول باید مال شغل کاربر و در سطح او باز شده باشد."""
    if user.job_key is None:
        return None, JobResult.NO_JOB
    product = jd.PRODUCT_BY_KEY.get(product_key)
    job = jd.JOB_OF_PRODUCT.get(product_key)
    if product is None or job is None or job.key != user.job_key:
        return None, JobResult.INVALID
    if product.unlock_level > user.level:
        return None, JobResult.PRODUCT_LOCKED
    return product, None


async def buy_raw_material(
    session: AsyncSession, user: User, product_key: str, quantity: int = 1
) -> JobOutcome:
    product, err = _product_for_user(user, product_key)
    if err:
        return JobOutcome(err)
    if quantity < 1:
        return JobOutcome(JobResult.INVALID)

    total = product.raw_price * quantity
    if user.toman < total:
        return JobOutcome(JobResult.INSUFFICIENT_TOMAN, total - user.toman)

    user.toman -= total
    row = (
        await session.execute(
            select(UserRawMaterial).where(
                UserRawMaterial.user_id == user.id, UserRawMaterial.product_key == product_key
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(UserRawMaterial(user_id=user.id, product_key=product_key, quantity=quantity))
    else:
        row.quantity += quantity
    await session.flush()
    return JobOutcome(JobResult.SUCCESS, total)


# ---------------------------------------------------------------------------
# تولید
# ---------------------------------------------------------------------------


async def start_production(session: AsyncSession, user: User, product_key: str) -> JobOutcome:
    product, err = _product_for_user(user, product_key)
    if err:
        return JobOutcome(err)
    if await get_active_production(session, user) is not None:
        return JobOutcome(JobResult.ALREADY_PRODUCING)

    raw = (
        await session.execute(
            select(UserRawMaterial).where(
                UserRawMaterial.user_id == user.id, UserRawMaterial.product_key == product_key
            )
        )
    ).scalar_one_or_none()
    if raw is None or raw.quantity < 1:
        return JobOutcome(JobResult.NO_RAW_MATERIAL)

    raw.quantity -= 1
    session.add(
        UserProduction(
            user_id=user.id,
            product_key=product.key,
            dhikr_done=0,
            dhikr_required=jd.DHIKR_PER_BATCH,
            started_at=_now(),
        )
    )
    await session.flush()
    return JobOutcome(JobResult.SUCCESS)


async def apply_production_dhikr(session: AsyncSession, user: User) -> ProductionProgress | None:
    """
    بعد از هر ذکر معتبرِ ثبت‌شده صدا زده می‌شود. اگر کاربر تولید فعال دارد یک واحد جلو
    می‌رود؛ با رسیدن به تعداد لازم، محصول (تعداد از سطح ابزار، ستاره‌ی هر واحد از جدول
    شانس) به انبار اضافه می‌شود. اگر تولیدی نبود None.
    """
    if user.job_key is None:
        return None
    prod = await get_active_production(session, user)
    if prod is None:
        return None

    prod.dhikr_done += 1
    progress = ProductionProgress(
        product_key=prod.product_key, done=prod.dhikr_done, required=prod.dhikr_required
    )

    if prod.dhikr_done >= prod.dhikr_required:
        produced = jd.roll_batch(max(user.tool_level, jd.TOOL_START_LEVEL))
        for stars, qty in produced.items():
            row = (
                await session.execute(
                    select(UserProduct).where(
                        UserProduct.user_id == user.id,
                        UserProduct.product_key == prod.product_key,
                        UserProduct.stars == stars,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    UserProduct(
                        user_id=user.id, product_key=prod.product_key, stars=stars, quantity=qty
                    )
                )
            else:
                row.quantity += qty
        await session.delete(prod)
        progress.completed = True
        progress.produced = produced

    await session.flush()
    return progress
