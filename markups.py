from gettext import gettext

from telebot.types import ReplyKeyboardMarkup, \
    KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, \
    InlineQueryResultArticle, InputTextMessageContent

import const
from models import List

_ = gettext


def main_mp(chat_id):
    lists = List.select().where(List.owner == chat_id)

    mp = ReplyKeyboardMarkup(row_width=1)
    if len(lists) > 0:
        mp.row(KeyboardButton(_("➕ Create list ➕")), KeyboardButton(_("✖ Delete list ✖")))
    else:
        mp.row(KeyboardButton(_("➕ Create list ➕")))
    for list_ in lists:
        if list_ != list_.subscribed_by:
            mp.add(KeyboardButton("🔗 📝 " + list_.name))
        else:
            mp.add(KeyboardButton("📝 " + list_.name))
    mp.add(KeyboardButton(_("⚙️ Settings ⚙️")))
    if chat_id in const.admins:
        mp.add("📢 Рассылка")
    return mp


def settings(lang):
    mp = InlineKeyboardMarkup(row_width=1)
    mp.add(
        InlineKeyboardButton(const.languages[lang][0] + _(" Change language"), callback_data='change_lang'),
        InlineKeyboardButton(_("Share list"), switch_inline_query="share lists")  # todo: redo
    )

    return mp


def languages():
    mp = InlineKeyboardMarkup(row_width=1)
    mp.add(*(InlineKeyboardButton(i[1][0] + ' ' + i[1][1], callback_data="swap_lang_" + i[0]) for i in
             const.languages.items()))
    return mp


def list_mp(list_id):
    list_ = List.get_by_id(list_id)
    list_ = List.get_by_id(list_.subscribed_by_id)

    mp = InlineKeyboardMarkup(row_width=1)
    for item in list_.items:
        if item.tag:
            s = "🔘 %s" % item.name
        else:
            s = "⚪ %s" % item.name
        mp.add(InlineKeyboardButton(s, callback_data="upd_list" + str(list_id) + "." + str(item.id)))
    if len(list_.items) > 0:
        mp.row(
            InlineKeyboardButton(_("➕ Add item"), callback_data="add_item_%i" % list_id),
            InlineKeyboardButton(_("🔗 Share"), switch_inline_query=list_.name),
            InlineKeyboardButton(_("❌ Delete item"), callback_data="delete_items_%i" % list_id),
        )
    else:
        mp.row(
            InlineKeyboardButton(_("➕ Add item"), callback_data="add_item_%i" % list_id),
            InlineKeyboardButton(_("🔗 Share"), switch_inline_query=list_.name),
        )
    return mp


def delete_list_mp(chat_id):
    lists = List.select().where(List.owner == chat_id)

    mp = ReplyKeyboardMarkup(row_width=1)
    mp.add(
        *(KeyboardButton("❌ 📝 " + list_.name) for list_ in lists)
    )
    mp.add(KeyboardButton(_("🔙 Back")))

    return mp


def ltos(l):
    return ",".join((str(i) for i in l))


def delete_items_mp(spotted: list, list_id):
    list_ = List.get_by_id(list_id)
    orig_list = List.get_by_id(list_.subscribed_by)

    mp = InlineKeyboardMarkup(row_width=1)
    for item in orig_list.items:
        spt = spotted.copy()
        if item.id in spotted:
            s = "💔 %s" % item.name
            spt.remove(item.id)
        else:
            s = "❤ %s" % item.name
            spt.append(item.id)
        cdata = "spt" + str(list_id) + '.' + ltos(spt)
        mp.add(InlineKeyboardButton(s, callback_data=cdata))
    if len(spotted) == 0:
        mp.add(InlineKeyboardButton(_("🔙 Back"), callback_data="upd_list" + str(list_id) + '.'))
    else:
        mp.add(InlineKeyboardButton(_("❌ Delete"), callback_data="cmt" + str(list_id) + '.' + ltos(spotted)))
    return mp


def subscribe_btn(list_id, me):
    mp = InlineKeyboardMarkup()
    mp.add(InlineKeyboardButton(_("Subscribe"), url=f"https://t.me/{me.username}?start=sub{list_id}"))
    return mp


def inline_share_list(lists, me):
    result = [
        *(InlineQueryResultArticle(
            id=list_.id,
            title=list_.name,
            input_message_content=InputTextMessageContent(_("Subscribe to my list {}").format(list_.name)),
            reply_markup=subscribe_btn(list_.id, me)
        ) for list_ in lists),
    ]
    return result


def dist_conf():
    mp = ReplyKeyboardMarkup(one_time_keyboard=True, row_width=2)
    mp.add(
        KeyboardButton("Да"),
        KeyboardButton("Нет"),
    )
    return mp


# Start
def start_lang():
    mp = InlineKeyboardMarkup(row_width=1)
    mp.add(
        *(InlineKeyboardButton(i[1][0] + ' ' + i[1][1], callback_data="swap_start_lang_" + i[0]) for i in
          const.languages.items())
    )
    return mp
