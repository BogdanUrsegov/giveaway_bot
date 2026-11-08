from aiogram.fsm.state import State, StatesGroup


class GiveawayCreate(StatesGroup):
    title = State()
    description = State()
    ticket_price = State()
    winners_count = State()
    max_tickets_per_user = State()
    closes_at = State()
    photo = State()
    channel = State()
