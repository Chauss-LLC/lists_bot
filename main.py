# -*- encoding: utf-8 -*-
from gettext import translation, gettext, ngettext
from time import sleep

import telebot
import telebot.types as types
from flask import Flask, request, abort

import const
import markups as mps
from models import User, List, Item, DoesNotExist, db

bot = telebot.TeleBot(token=const.token, threaded=False)

app = Flask(__name__)
bot.remove_webhook()
bot.set_webhook(f"https://{const.host}/{const.token}/",
                certificate=open(const.SSL_CERT, 'r'))

_ = gettext
list_to_edition = {}  # {<user_id>: <list_id>}
me = bot.get_me()  # Bot info in User format
msg_id_to_distr = 0  # int message id for distributing

for language in const.languages:
    const.languages[language].append(translation("shop_list", "./locales", languages=[language]))


def set_language(lang):
    global _
    try:
        tr = const.languages[lang][2]  # translation
        tr.install()
        _ = tr.gettext
        mps._ = tr.gettext
    except KeyError:
        _ = gettext
        mps._ = gettext


@app.before_request
def open_db():
    db.connect(reuse_if_open=True)


@app.teardown_request
def close_db(__):
    if not db.is_closed():
        db.close()


@app.route(f'/{const.token}/', methods=['POST', 'GET'])
def route():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        try:
            uid = update.message or \
                  update.callback_query or \
                  update.inline_query
            uid = uid.from_user.id
            user = User.get_by_id(uid)
        except (DoesNotExist, AttributeError):
            user = User(language_code=const.default_lang)
        set_language(user.language_code)
        try:
            bot.process_new_updates([update])
        except telebot.apihelper.ApiException:
            pass
        return 'ok'
    else:
        abort(403)


def delete_message(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except telebot.apihelper.ApiException:
        pass


@bot.message_handler(commands=["start", "restart"])
def start(msg: types.Message):
    u_lang = msg.from_user.language_code if msg.from_user.language_code in const.languages else const.default_lang
    user, created = User.get_or_create(
        id=msg.from_user.id,
        defaults={
            'username': msg.from_user.username,
            'first_name': msg.from_user.first_name,
            'last_name': msg.from_user.last_name,
            'language_code': u_lang
        }
    )
    params = msg.text.split(' ')
    if len(params) > 1 and params[1] == 'createlist':
        create_list(msg)
    elif len(params) > 1 and params[1].startswith("sub"):
        list_ = List.get_by_id(int(params[1][3:]))
        msg.text = f"📝 {list_.name}"
        new_list, created = List.get_or_create(name=list_.name, owner=user.id,
                                               defaults={"subscribed_by": list_})
        if created:
            bot.send_message(msg.from_user.id, _("You subscribed to _{}_ list").format(list_.name),
                             parse_mode='markdown',
                             reply_markup=mps.main_mp(user.id))
            text = f"🔗 📝 *{new_list.name}*"
        else:
            delete_message(msg.chat.id, list_.last_message_id)
            bot.send_message(msg.chat.id, _("You already have list with same name"), reply_markup=mps.main_mp(user.id))
            text = f"📝 *{new_list.name}*"
        sent = bot.send_message(msg.chat.id, text, reply_markup=mps.list_mp(new_list.id),
                                parse_mode='markdown')
        new_list.last_message_id = sent.message_id
        new_list.save()
    else:
        bot.send_message(msg.from_user.id, _("Hello. Create your first list."), reply_markup=mps.main_mp(user.id))


@bot.message_handler(regexp="^⚙ *")
def settings(msg):
    user = User.get_by_id(msg.chat.id)
    bot.send_message(msg.from_user.id,
                     _("*⚙️ Settings ⚙️*"),
                     reply_markup=mps.settings(user.language_code),
                     parse_mode='markdown')


@bot.message_handler(regexp="^➕ *")
def create_list(msg):
    user = User.get_by_id(msg.chat.id)
    sent_msg = bot.send_message(chat_id=user.id,
                                text=_("➕ *Creating list* ➕\n 📝 Write name of your list\n\n "
                                       "`You can name it like market where you gonna shopping`\n\n"
                                       "Type '-' for cancel"),
                                reply_markup=types.ForceReply(), parse_mode='markdown')
    bot.register_next_step_handler(sent_msg, adding_list)


def adding_list(msg):
    user = User.get_by_id(msg.chat.id)
    if msg.text == '-':
        bot.send_message(msg.chat.id, _("Canceled"), reply_markup=mps.main_mp(msg.chat.id))
        return
    elif len(msg.text) > 255:
        bot.send_message(msg.chat.id, _("Too long name. Max length is 255 symbols. Try another name: "))
        bot.register_next_step_handler_by_chat_id(msg.chat.id, adding_list)
        return
    creating_list = List.get_or_none((List.name == msg.text) & (List.owner == user))
    if creating_list is not None:
        sent_msg = bot.send_message(chat_id=msg.chat.id,
                                    text=_("You have already created list with this name. Try another:"),
                                    reply_markup=types.ForceReply())
        bot.register_next_step_handler(sent_msg, adding_list)
    else:
        creating_list = List.create(name=msg.text, owner=user)
        creating_list.subscribed_by = creating_list
        creating_list.save()
        bot.send_message(chat_id=msg.from_user.id,
                         text=_("List _%s_ created") % msg.text, parse_mode='markdown',
                         reply_markup=mps.main_mp(user.id))
        msg_list = bot.send_message(chat_id=msg.from_user.id, text="📝 *%s*" % msg.text,
                                    parse_mode='markdown', reply_markup=mps.list_mp(creating_list.id))
        creating_list.last_message_id = msg_list.message_id
        creating_list.save()


@bot.message_handler(regexp="^✖ *")
def delete_list(msg):
    user = User.get_by_id(msg.chat.id)
    bot.send_message(msg.chat.id, _("Choose list for deleting"), reply_markup=mps.delete_list_mp(user.id))
    bot.register_next_step_handler_by_chat_id(msg.chat.id, deleting_list)


def deleting_list(msg):
    user = User.get_by_id(msg.chat.id)
    if msg.text.startswith("🔙 "):
        bot.send_message(msg.chat.id, _("Canceled"), reply_markup=mps.main_mp(user.id))
        return
    try:
        list_name = msg.text[4:]
        list_ = List.get((List.name == list_name) & (List.owner == user))
    except (IndexError, DoesNotExist):
        bot.send_message(msg.chat.id, _("This list doesn't exist, choose from keyboard below"),
                         reply_markup=mps.delete_list_mp(user.id))
        bot.register_next_step_handler_by_chat_id(user.id, deleting_list)
        return
    if list_ == list_.subscribed_by:
        for sub in List.select().where(List.subscribed_by == list_):
            bot.delete_message(sub.owner.id, sub.last_message_id)
            sub.delete_instance()
            bot.send_message(sub.owner.id, _("List _%s_ was deleted") % sub.name,
                             reply_markup=mps.main_mp(sub.owner.id),
                             parse_mode='markdown', disable_notification=True)
    else:
        bot.delete_message(msg.chat.id, list_.last_message_id)
        list_.delete_instance()
        bot.send_message(msg.chat.id, _("You were successfully unsubscribed from list _%s_ ") % list_name,
                         reply_markup=mps.main_mp(msg.chat.id), parse_mode='markdown')


@bot.callback_query_handler(func=lambda call: call.data == 'change_lang')
def language_changing(c):
    user = User.get_by_id(c.message.chat.id)
    bot.edit_message_text(text=_("*⚙️ Settings ⚙️*\nChoose a language:"),
                          chat_id=user.id,
                          message_id=c.message.message_id,
                          reply_markup=mps.languages(), parse_mode='markdown')
    bot.answer_callback_query(c.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("swap_lang"))
def swap_language(c):
    user = User.get_by_id(c.message.chat.id)
    lang = c.data[-2:]
    user.language_code = lang
    user.save()
    set_language(lang)
    bot.edit_message_text(text=_("*⚙️ Settings ⚙️*"),
                          chat_id=user.id,
                          message_id=c.message.message_id,
                          reply_markup=mps.settings(lang), parse_mode='markdown')

    bot.send_message(chat_id=user.id,
                     text=_("Language changed to ") + const.languages[lang][0] + ' ' + const.languages[lang][1],
                     reply_markup=mps.main_mp(c.message.chat.id))
    bot.answer_callback_query(c.id)


@bot.message_handler(regexp="^[📝 , 🔗 ]  *")
def show_list(msg):
    user = User.get_by_id(msg.chat.id)
    if msg.text.startswith("🔗 "):
        list_name = msg.text[4:]
    else:
        list_name = msg.text[2:]
    try:
        list_ = List.get((List.owner == user) & (List.name == list_name))
    except DoesNotExist:
        bot.send_message(user.id, _("This list doesn't exist"), reply_markup=mps.main_mp(user.id))
        return
    list_name = msg.text
    new_list_msg = bot.send_message(chat_id=user.id,
                                    text=f"*{list_name}*",
                                    parse_mode='markdown',
                                    reply_markup=mps.list_mp(list_.id))
    try:
        bot.delete_message(msg.chat.id, list_.last_message_id)
    except telebot.apihelper.ApiException:
        pass
    list_.last_message_id = new_list_msg.message_id
    list_.save()


@bot.callback_query_handler(func=lambda c: c.data.startswith("add_item"))
def enter_item(c):
    user = User.get_by_id(c.message.chat.id)
    list_id = int(c.data[9:])
    list_ = List.get_by_id(list_id)
    original_list = list_.subscribed_by

    s = "📝 *%s*\n\n" % list_.name
    for item in original_list.items:
        if item.tag:
            s += "🔘 %s\n" % item.name
        else:
            s += "⚪ %s\n" % item.name
    s += _("*Insert new item to buy: *")
    bot.send_message(chat_id=user.id,
                     text=s,
                     reply_markup=types.ForceReply(), parse_mode='markdown')
    try:
        bot.delete_message(c.message.chat.id, list_.last_message_id)
    except telebot.apihelper.ApiException:
        pass
    list_to_edition.update({user.id: list_id})
    bot.register_next_step_handler_by_chat_id(user.id, add_item)


def add_item(msg):
    user = User.get_by_id(msg.chat.id)
    list_id = list_to_edition[user.id]
    list_ = List.get_by_id(list_id)
    orig_list = list_.subscribed_by
    items = [
        Item(name=item_name, list_id=orig_list.id)
        for string in msg.text.split('\n')
        for item_name in string.split(',')
        if len(item_name) <= 255
    ]
    if len(items) == 0:
        bot.send_message(msg.chat.id, _("Too long item name. Cancelled."))
    else:
        bot.send_message(msg.chat.id, ngettext("Item created", "Items created", len(items)),
                         parse_mode="markdown", reply_markup=mps.main_mp(msg.chat.id), disable_notification=True)
        Item.bulk_create(items)
    sent = bot.send_message(msg.chat.id, "📝 *%s*" % list_.name, reply_markup=mps.list_mp(list_id),
                            parse_mode='markdown')
    list_.last_message_id = sent.message_id
    list_.save()
    for sub in orig_list.subs:
        if sub == list_:
            continue
        bot.edit_message_reply_markup(chat_id=sub.owner.id,
                                      message_id=sub.last_message_id,
                                      reply_markup=mps.list_mp(sub.id))


@bot.callback_query_handler(func=lambda c: c.data.startswith("delete_items"))
def delete_items(c):
    user = User.get_by_id(c.message.chat.id)
    bot.answer_callback_query(c.id, _("Choose items for deleting"))
    list_id = int(c.data[13:])
    bot.edit_message_reply_markup(user.id, c.message.message_id,
                                  reply_markup=mps.delete_items_mp([], list_id))


@bot.callback_query_handler(func=lambda c: c.data.startswith("spt"))
def spotting_delete_items(c):
    dot = c.data.find('.')
    list_id = int(c.data[3:dot])
    spotted = [int(i) for i in c.data[dot + 1:].split(',') if i != '']
    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                  reply_markup=mps.delete_items_mp(spotted, list_id))


@bot.callback_query_handler(func=lambda c: c.data.startswith('cmt'))
def commit_deleting(c):
    dot = c.data.find('.')
    list_id = int(c.data[3:dot])
    list_ = List.get_by_id(list_id)

    spt_s = c.data[dot + 1:]
    spotted = [int(i) for i in spt_s.split(',')]

    Item.delete().where(Item.id.in_(spotted)).execute()
    for sub in List.select().where(List.subscribed_by == list_.subscribed_by):
        bot.edit_message_reply_markup(sub.owner.id, sub.last_message_id,
                                      reply_markup=mps.list_mp(sub.id))


@bot.callback_query_handler(func=lambda c: c.data.startswith("upd_list"))
def update_list(c):
    dot = c.data.find('.')
    list_id = int(c.data[8:dot])
    list_ = List.get_by_id(list_id)
    if c.data[dot + 1:]:
        item_id = int(c.data[dot + 1:])
        item = Item.get_by_id(item_id)
        item.tag = not item.tag
        item.save()
        for sub in List.select().where(List.subscribed_by == list_.subscribed_by):
            bot.edit_message_reply_markup(sub.owner.id, sub.last_message_id,
                                          reply_markup=mps.list_mp(list_id))
        bot.answer_callback_query(c.id)
    else:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                      reply_markup=mps.list_mp(list_id))


# # # # # # Callback query # # # # # # #
@bot.inline_handler(func=lambda q: List.select().where((List.owner == q.from_user.id) & (List.name == q.query)))
def share_table(q: types.InlineQuery):
    list_ = List.get((List.owner == q.from_user.id) & (List.name == q.query))
    bot.answer_inline_query(q.id, mps.inline_share_list((list_,), me), cache_time=5, is_personal=True,
                            switch_pm_text=_("➕ Create list ➕"), switch_pm_parameter='createlist')


@bot.inline_handler(func=lambda q: True)
def share_table(q: types.InlineQuery):
    lists = List.select().where(List.owner == q.from_user.id)
    bot.answer_inline_query(q.id, mps.inline_share_list(lists, me), cache_time=5, is_personal=True,
                            switch_pm_text=_("➕ Create list ➕"), switch_pm_parameter='createlist')


@bot.message_handler(func=lambda msg: msg.reply_to_message is not None)
def name_changer(msg: types.Message):
    try:
        list_ = List.get(List.name == msg.reply_to_message.text[2:])
        bot.edit_message_text(f"📝 *{msg.text}*", msg.chat.id, list_.last_message_id, parse_mode='markdown',
                              reply_markup=mps.list_mp(list_.id))
        list_.name = msg.text
        list_.save()
        bot.send_message(msg.chat.id, _("List name changed."), reply_markup=mps.main_mp(msg.chat.id))
    except (DoesNotExist, IndexError):
        pass


@bot.message_handler(func=lambda msg: msg.chat.id in const.admins and msg.text.startswith("📢"))
def distribution(msg):
    m = bot.send_message(msg.chat.id, "Введите текст для рассылки: \n_Для отмены введите '-'_",
                         reply_markup=telebot.types.ForceReply(),
                         parse_mode='markdown')
    bot.register_for_reply(m, confirm_distribution)


def confirm_distribution(msg):
    if msg.text == '-':
        bot.send_message(msg.chat.id, "Оменено", reply_markup=mps.main_mp(msg.chat.id))
        return
    global msg_id_to_distr
    msg_id_to_distr = msg.message_id
    bot.forward_message(msg.chat.id, msg.chat.id, msg.message_id, disable_notification=True)
    bot.send_message(msg.chat.id, "Ваше сообщение будет выглядеть так ⬆. \n*Разослать?*", parse_mode='markdown',
                     reply_markup=mps.dist_conf())
    bot.register_next_step_handler_by_chat_id(msg.chat.id, sender)


def sender(msg):
    if msg.text.upper() != "ДА":
        bot.send_message(msg.chat.id, "Рассылка отменена.", reply_markup=mps.main_mp(msg.chat.id))
        return
    cnt = 0
    cnt_sccs = 0
    cnt_unsccs = 0
    cnt_blocked = 0
    for user in User.select():
        try:
            if cnt % 20 == 0 and cnt > 0:
                sleep(0.5)
            bot.forward_message(user.id, msg.chat.id, msg_id_to_distr, disable_notification=True)
            cnt_sccs += 1
        except telebot.apihelper.ApiException as e:
            if e.result.status_code == 429:
                sleep(1)
                bot.send_message(msg.chat.id, "Слишком много сообщений в секунду, подождём...")

            elif e.result.status_code in (403, 400):
                cnt_blocked += 1
                continue
            else:
                cnt_unsccs += 1
                continue
        finally:
            cnt += 1
    bot.send_message(msg.chat.id, f"Сообщение было отправлено *{cnt_sccs}* пользователям.\n"
                                  f"Бот заблокирован у *{cnt_blocked}* пользователей.\n"
                                  f"Во время рассылки было поймано *{cnt_unsccs}* ошибок.",
                     reply_markup=mps.main_mp(msg.chat.id), parse_mode='markdown')


@bot.message_handler(func=lambda msg: True)
def what(msg):
    bot.send_message(msg.from_user.id,
                     _("I don't understand you. If you have some problems with bot just type /restart"))


def recreate_tables():
    with db:
        db.drop_tables([User, List, Item])
        db.create_tables([User, List, Item])
