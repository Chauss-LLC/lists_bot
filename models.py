from peewee import *

# db = SqliteDatabase("temporary.db", pragmas={"foreign_keys": "on"}) #
import const

db = MySQLDatabase('shop_list_db', thread_safe=True,
                   charset='utf8mb4',
                   use_unicode=True,
                   host='localhost',
                   port=3306,
                   user=const.DB_USER,
                   password=const.DB_PASS)


class User(Model):
    id = IntegerField(unique=True, primary_key=True)
    username = CharField(null=True, unique=True)
    first_name = CharField()
    last_name = CharField(null=True)
    language_code = FixedCharField(null=True, max_length=10)

    class Meta:
        database = db


class List(Model):
    id = AutoField(unique=True, primary_key=True)
    name = CharField()
    owner = ForeignKeyField(User, related_name='lists')
    last_message_id = IntegerField(null=True, unique=True)
    subscribed_by = ForeignKeyField('self', backref='subs', null=True, on_delete='CASCADE')

    class Meta:
        database = db


class Item(Model):
    id = AutoField(unique=True, primary_key=True)
    name = CharField()
    list_id = ForeignKeyField(List, related_name='items', on_delete="CASCADE")
    tag = BooleanField(default=0)

    class Meta:
        database = db
