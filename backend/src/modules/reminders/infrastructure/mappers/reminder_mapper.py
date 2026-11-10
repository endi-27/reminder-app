from decimal import Decimal

from src.infrastructure.db.mappers import BaseMapper
from src.modules.reminders.domain.aggregates import (
    AnniversaryReminder,
    DeadlineTaskReminder,
    MedicationReminder,
    OpenTaskReminder,
    ReminderAggregate,
    SubscriptionReminder,
)
from src.modules.reminders.domain.enums import CurrencyCode, ReminderType
from src.modules.reminders.domain.value_objects import (
    LeadTimes,
    Money,
    parse_schedule_config,
    serialize_schedule_config,
)
from src.modules.reminders.infrastructure.models import ReminderModel


class ReminderMapper(BaseMapper[ReminderAggregate, ReminderModel]):
    """
    Поліморфний Data Mapper для Single Table Inheritance таблиці reminders.

    Трансформує спільний запис ReminderModel у відповідний чистий доменний
    агрегат (з 5 доступних) та виконує зворотну дегідрацію стану агрегата у модель.
    """

    def to_domain(self, model: ReminderModel) -> ReminderAggregate:
        """Трансформація ORM-моделі ReminderModel у відповідний чистий доменний агрегат."""
        schedule_config = parse_schedule_config(model.schedule_logic, model.schedule_config)
        lead_times = LeadTimes(model.lead_times)

        if model.reminder_type == ReminderType.ANNIVERSARY:
            return AnniversaryReminder(
                id=model.id,
                user_id=model.user_id,
                reminder_type=model.reminder_type,
                schedule_logic=model.schedule_logic,
                title=model.title,
                description=model.description,
                status=model.status,
                next_trigger_at=model.next_trigger_at,
                schedule_config=schedule_config,
                lead_times=lead_times,
                created_at=model.created_at,
                updated_at=model.updated_at,
                deleted_at=model.deleted_at,
                version=model.version,
            )

        if model.reminder_type == ReminderType.OPEN_TASK:
            return OpenTaskReminder(
                id=model.id,
                user_id=model.user_id,
                reminder_type=model.reminder_type,
                schedule_logic=model.schedule_logic,
                title=model.title,
                description=model.description,
                status=model.status,
                next_trigger_at=model.next_trigger_at,
                schedule_config=schedule_config,
                lead_times=lead_times,
                created_at=model.created_at,
                updated_at=model.updated_at,
                deleted_at=model.deleted_at,
                version=model.version,
                base_priority=model.base_priority,
            )

        if model.reminder_type == ReminderType.DEADLINE_TASK:
            due_dt = model.due_datetime if model.due_datetime is not None else model.next_trigger_at
            return DeadlineTaskReminder(
                id=model.id,
                user_id=model.user_id,
                reminder_type=model.reminder_type,
                schedule_logic=model.schedule_logic,
                title=model.title,
                description=model.description,
                status=model.status,
                next_trigger_at=model.next_trigger_at,
                schedule_config=schedule_config,
                lead_times=lead_times,
                created_at=model.created_at,
                updated_at=model.updated_at,
                deleted_at=model.deleted_at,
                version=model.version,
                due_datetime=due_dt,
                base_priority=model.base_priority,
                calculated_priority=model.calculated_priority,
            )

        if model.reminder_type == ReminderType.SUBSCRIPTION:
            currency_code = model.currency or CurrencyCode.UAH
            reg_amount = (
                Money(amount=model.regular_amount, currency=currency_code)
                if model.regular_amount is not None
                else Money(Decimal("0.00"), currency_code)
            )
            disc_amount = (
                Money(amount=model.discount_amount, currency=currency_code)
                if model.discount_amount is not None
                else None
            )
            return SubscriptionReminder(
                id=model.id,
                user_id=model.user_id,
                reminder_type=model.reminder_type,
                schedule_logic=model.schedule_logic,
                title=model.title,
                description=model.description,
                status=model.status,
                next_trigger_at=model.next_trigger_at,
                schedule_config=schedule_config,
                lead_times=lead_times,
                created_at=model.created_at,
                updated_at=model.updated_at,
                deleted_at=model.deleted_at,
                version=model.version,
                regular_amount=reg_amount,
                is_trial=model.is_trial,
                trial_end_date=model.trial_end_date,
                discount_amount=disc_amount,
                discount_cycles_total=model.discount_cycles_total,
                discount_cycles_remaining=model.discount_cycles_remaining,
            )

        if model.reminder_type == ReminderType.MEDICATION:
            return MedicationReminder(
                id=model.id,
                user_id=model.user_id,
                reminder_type=model.reminder_type,
                schedule_logic=model.schedule_logic,
                title=model.title,
                description=model.description,
                status=model.status,
                next_trigger_at=model.next_trigger_at,
                schedule_config=schedule_config,
                lead_times=lead_times,
                created_at=model.created_at,
                updated_at=model.updated_at,
                deleted_at=model.deleted_at,
                version=model.version,
                course_duration_days=model.course_duration_days,
                medication_start_date=model.medication_start_date,
                medication_end_date=model.medication_end_date,
                strict_schedule=model.strict_schedule,
            )

        raise ValueError(f"Непідтримуваний тип нагадування для мапінгу: {model.reminder_type}")

    def to_model(self, entity: ReminderAggregate) -> ReminderModel:
        """Трансформація чистого доменного агрегата в ORM-модель ReminderModel."""
        model = ReminderModel(
            id=entity.id,
            user_id=entity.user_id,
            reminder_type=entity.reminder_type,
            schedule_logic=entity.schedule_logic,
            title=entity.title,
            description=entity.description,
            status=entity.status,
            next_trigger_at=entity.next_trigger_at,
            schedule_config=serialize_schedule_config(entity.schedule_config),
            lead_times=entity.lead_times.to_list(),
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            deleted_at=entity.deleted_at,
            version=entity.version,
        )

        if isinstance(entity, OpenTaskReminder):
            model.base_priority = entity.base_priority
        elif isinstance(entity, DeadlineTaskReminder):
            model.due_datetime = entity.due_datetime
            model.base_priority = entity.base_priority
            model.calculated_priority = entity.calculated_priority
        elif isinstance(entity, SubscriptionReminder):
            model.regular_amount = entity.regular_amount.amount
            model.currency = entity.regular_amount.currency
            model.is_trial = entity.is_trial
            model.trial_end_date = entity.trial_end_date
            model.discount_amount = entity.discount_amount.amount if entity.discount_amount else None
            model.discount_cycles_total = entity.discount_cycles_total
            model.discount_cycles_remaining = entity.discount_cycles_remaining
        elif isinstance(entity, MedicationReminder):
            model.course_duration_days = entity.course_duration_days
            model.medication_start_date = entity.medication_start_date
            model.medication_end_date = entity.medication_end_date
            model.strict_schedule = entity.strict_schedule

        return model
