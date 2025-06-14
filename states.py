from aiogram.fsm.state import State, StatesGroup


class OrderFSM(StatesGroup):
    awaiting_payment_type = State()
    awaiting_item_name = State()
    awaiting_add_confirmation = State()
