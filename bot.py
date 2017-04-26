#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from queue import Queue
from threading import Thread
from telegram import Bot
from telegram.ext import Dispatcher, Updater
from telegram.ext import CommandHandler
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date
import os
import requests
import string
import logging
import time
import redis
from pytz import timezone

TOKEN = str(os.environ.get('TOKEN'))
logging.basicConfig(level=logging.INFO)
HOST = str(os.environ.get('OPENSHIFT_REDIS_HOST'))
PORT = str(os.environ.get('OPENSHIFT_REDIS_PORT'))
PASS = str(os.environ.get('REDIS_PASSWORD'))
red = redis.Redis(host=HOST, port=PORT, db=0, password=PASS, decode_responses=True)
leave = string.punctuation.replace(',', '').replace('-', ' ')
tz = timezone('Asia/Yekaterinburg')
URL = 'http://raspisanie.ugatu.su/raspisanie/'
TEACHER_URL = 'http://lk.ugatu.su/teacher/#timetable'
client = requests.session()
page = client.get(URL)
teacher_page = client.get(TEACHER_URL)
csrf = page.cookies['csrftoken']
bs = BeautifulSoup(page.text, 'lxml')
teachbs = BeautifulSoup(teacher_page.text, 'lxml')
try:
    sem = bs.find(id='SemestrSchedule').contents[3]['value']
    int(sem)
    red.set('sem', sem)
    week = bs.find('h3').next_sibling.next_sibling.contents[0].contents[0]
    int(week)
    red.set('week', week)
except ValueError:
    red.set('sem', '4')
    red.set('week', '1')
todate = datetime.now(tz=tz).date()
red.set('current_date', str(todate))
red.set('current_day', str(todate.weekday()))


def find_week():
    todate = datetime.now(tz=tz).date()
    savedate = red.get('current_date')
    saveday = red.get('current_day')
    week = red.get('week')
    if todate > datetime.strptime(str(savedate), '%Y-%m-%d').date() and todate.weekday() <= int(saveday):
        page = client.get(URL)
        bs = BeautifulSoup(page.text, 'lxml')
        week = bs.find('h3').next_sibling.next_sibling.contents[0].contents[0]
        red.set('current_date', str(todate))
        red.set('current_day', str(todate.weekday()))
        red.set('week', week)
    return week


def start(bot, update):
    message = 'Чтобы начать работу с ботом отправьте команду:\n' + \
             '/set факультет группа, например "/set ФИРТ БА-102М"\n' + \
             'Затем, используйте одну из следующих команд для получения расписания на:\n' + \
             '/today - сегодня\n' + \
             '/tomorrow - завтра\n' + \
             '/after - послезавтра\n' + \
             '/monday - понедельник\n' + \
             '/tuesday - вторник\n' + \
             '/wednesday - среда\n' + \
             '/thursday - четверг\n' + \
             '/friday - пятница\n' + \
             '/saturday - суббота\n' + \
             '/date день месяц - расписание на конкретный день, например "/date 1 3" это расписание на первое марта\n' + \
             '/exam - расписание экзаменов\n' + \
             '/teacher Фамилия Имя Отчество - расписание преподавателя (тестовая версия). Вводить можно и только Фамилия Имя, ' \
             'или только Имя Отчество или вообще что-то одно, но вернется по первому совпадению.\n' + \
             '/changelog - последнее нововведение\n' + \
             'К каждой из команд, относящихся к дням недели можно добавить номер недели, например "/monday 5" вернет ' \
             'расписание на понедельник пятой недели. ' \
             'По умолчанию возвращается расписание на ближайший будущий день недели.'
    bot.sendMessage(chat_id=update.message.chat_id, text=message)


def exam(bot, update):
    id = update.message.chat_id
    if not (red.hexists(id, 'faculty') and red.hexists(id, 'year') and red.hexists(id, 'group')):
        bot.sendMessage(chat_id=update.message.chat_id, text='Сначала используйте команду "/set факультет группа"', parse_mode='markdown')
        return
    faculty = red.hget(id, 'faculty')
    year = red.hget(id, 'year')
    groupname = red.hget(id, 'group')
    #logging.log(logging.INFO, "group id " + groupname)
    param = dict(csrfmiddlewaretoken=csrf, faculty=faculty, klass=year)

    return_message = ''

    param['ScheduleType'] = 'Экзамены'
    param['group'] = groupname
    param['sem'] = sem
    param['view'] = 'ПОКАЗАТЬ'
    answer = client.post(URL, param)

    bs = BeautifulSoup(answer.text, 'lxml')

    for row in bs.findAll('tr'):
        if len(row.contents) != 0 and (not row.contents[1].contents[1].contents or len(row.contents[1].contents[1].contents) == 3):
            time = row.contents[0].contents[0].contents[0].contents[0]
            title = row.contents[1].contents[0].contents[0]
            date = ''
            place = ''
            teacher = ''
            if len(row.contents[0].contents[0]) >= 2:
                kind = row.contents[1].contents[3].contents[1] + '\n'
                date = '*' + row.contents[0].contents[0].contents[2] + '*\n'
                place = '_Аудитория:_ ' + row.contents[1].contents[2].contents[0] + '\n'
                if len(row.contents[1].contents[3].contents) >= 4:
                    teacher = row.contents[1].contents[3].contents[3] + '\n\n'
            else:
                kind = row.contents[1].contents[1].contents[1] + '\n\n'
            return_message += '*' + title + '*\n' + date + '_' + time + '_\n' + place + kind + teacher
    if return_message == '':
        return_message = 'Расписание отсутствует'
    bot.sendMessage(chat_id=update.message.chat_id, text=return_message, parse_mode='markdown')


def get_table(id, deltaday, needed_week, needed_date):
    if not (red.hexists(id, 'faculty') and red.hexists(id, 'year') and red.hexists(id, 'group')):
        return 'Сначала используйте команду "/set факультет группа"'
    faculty = red.hget(id, 'faculty')
    year = red.hget(id, 'year')
    groupname = red.hget(id, 'group')

    param = dict(csrfmiddlewaretoken=csrf, faculty=faculty, klass=year)

    return_message = ''
    param['ScheduleType'] = 'На дату'
    param['group'] = groupname
    #logging.log(logging.INFO, "group id " + groupname)
    param['week'] = '1'
    param['sem'] = sem
    param['view'] = 'ПОКАЗАТЬ'
    current_week = find_week()
    try:
        current_week_numb = int(current_week)
        if needed_week == -2:
            current_week = str(current_week_numb + 1)
        param['week'] = current_week
    except ValueError:
        return_message = 'Судя по всему с сайта неправильно спарсился текущий номер недели, дико извиняюсь \n\n'

    if needed_week != -1 and needed_week != -2:
        deltaday += 7 * (needed_week - current_week_numb)

    if not needed_date:
        needed_date = (datetime.now(tz=tz) + timedelta(days=deltaday)).date()

    now = datetime.now(tz=tz).date()
    delta = (needed_date - now).days
    current_week_numb += int(delta / 7.)
    if needed_date.weekday() < now.weekday() and delta > 0:
        current_week_numb += 1
    elif current_week_numb > needed_week > 0:
        current_week_numb = needed_week
    current_week = str(current_week_numb)
    param['week'] = current_week

    logging.log(logging.INFO, "week " + current_week)
    day = str(needed_date.day)
    month = str(needed_date.month)
    year = str(needed_date.year)
    dotdate = day + '.' + month + '.' + year
    param['date'] = dotdate
    startt = time.time()
    answer = client.post(URL, param)
    logging.log(logging.INFO, 'final request ' + str(time.time() - startt))
    beas = BeautifulSoup(answer.text, 'lxml')
    message_list = []
    for row in beas.findAll('td'):
        if len(row.contents) == 1 and len(row.contents[0]) > 4:
            # заголовок
            message_list.append('*' + row.contents[0] + ', ' + dotdate + '\n' + current_week + ' неделя*\n\n')
        elif len(row.contents) == 3 and len(row.contents[0]) == 1:
            # номер пары
            message_list.append('_' + row.contents[0].contents[0] + ':_ ' + row.contents[2].contents[0] + '\n')
        elif len(row.contents) > 0 and len(row.contents[0]) == 4:
            # информация о паре
            n = len(row.contents)
            for i in range(n):
                if len(row.contents[i].contents[3].contents[3].contents) != 0:
                    teacher = '_Преподаватель:_ ' + row.contents[i].contents[3].contents[3].contents[0] + '\n'
                else:
                    teacher = ''
                split = '\n---\n'
                if i == n - 1:
                    split = '\n\n'
                message_list.append(row.contents[i].contents[0].contents[0] + '\n' + \
                                    '_Аудитория:_ ' + row.contents[i].contents[2].contents[0] + '\n' + \
                                    teacher + \
                                    row.contents[i].contents[3].contents[1] + split)

    for message in message_list:
        index = message_list.index(message)
        if not ('пара:' in message and (index == len(message_list) - 1 or 'пара:' in message_list[index + 1])):
            return_message += message
    if return_message == '':
        return_message = 'Пар нет'
    return return_message


def today(bot, update):
    message = get_table(update.message.chat_id, 0, -1, '')
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode='markdown')


def tomorrow(bot, update):
    message = get_table(update.message.chat_id, 1, -1, '')
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode='markdown')


def after_tomorrow(bot, update):
    message = get_table(update.message.chat_id, 2, -1, '')
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode='markdown')


def monday(bot, update, args):
    for_day(bot, update, 0, args)


def tuesday(bot, update, args):
    for_day(bot, update, 1, args)


def wednesday(bot, update, args):
    for_day(bot, update, 2, args)


def thursday(bot, update, args):
    for_day(bot, update, 3, args)


def friday(bot, update, args):
    for_day(bot, update, 4, args)


def saturday(bot, update, args):
    for_day(bot, update, 5, args)


def for_day(bot, update, daynumber, args):
    needed_week = -1
    temp_message = ''
    if len(args) != 0:
        if len(args[0]) > 2:
            bot.sendMessage(chat_id=update.message.chat_id, text='Ты чо, шакал?')
        try:
            needed_week = int(args[0])
        except ValueError:
            temp_message = 'Ну нельзя же так, ну чего ты. Ну просили же цифры. На вот как обычно, раз так \n\n'

    current = datetime.now(tz=tz).weekday()
    if daynumber < current and len(args) == 0:
        daynumber += 7
        needed_week = -2
    message = get_table(update.message.chat_id, daynumber - current, needed_week, '')
    bot.sendMessage(chat_id=update.message.chat_id, text=temp_message + message, parse_mode='markdown')


def on_date(bot, update, args):
    if len(args) != 2 or len(args[0]) > 2 or len(args[1]) > 2:
        bot.sendMessage(chat_id=update.message.chat_id,
                        text='Пожалуйста, пришлите данные в корректном формате, например "/date 1 3"')
        return
    try:
        day = int(args[0])
        month = int(args[1])
    except ValueError:
        bot.sendMessage(chat_id=update.message.chat_id,
                        text='Пожалуйста, пришлите данные в корректном формате, например "/date 1 3"')
        return
    now = datetime.now(tz=tz).date()
    needed = date(year=now.year, month=month, day=day)
    message = get_table(update.message.chat_id, needed.weekday(), -1, needed)
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode='markdown')


def teacher(bot, update, args):
    return_message = ''
    if len(args) != 0:
        teacher_name = ''
        for arg in args:
            teacher_name += arg + ' '
        teacher_name = teacher_name.strip().lower()
        teacher_number = ''
        for option in teachbs.findAll('option'):
            if teacher_name in option.text.lower():
                teacher_number = option['value']
                teacher_name = option.text
                break
        if teacher_number != '':
            csrf = teacher_page.cookies['csrftoken']
            param = dict(csrfmiddlewaretoken=csrf, teacher=teacher_number)
            answer = client.post(TEACHER_URL, param)
            if 'Расписание отсутствует' in answer.text:
                bot.sendMessage(chat_id=update.message.chat_id, text='Расписание отсутствует.')
                return
            beas = BeautifulSoup(answer.text, 'lxml')
            return_message += add_symbols('*', find_week() + ' неделя\n')
            return_message += add_symbols('*', teacher_name) + '\n\n'
            for day_index in range(3, 14, 2):
                table = beas.findAll('tr')
                message = add_symbols('*', table[0].contents[day_index].text) + '\n'
                for pair_index in range(1, 7):
                    if len(table[pair_index].contents[day_index].contents) > 0:
                        pair_number = table[pair_index].contents[1].contents[0].text + ': '
                        pair_phrase = table[pair_index].contents[1].contents[2].text
                        pair = table[pair_index].contents[day_index].contents[0].contents[0].text
                        place = table[pair_index].contents[day_index].contents[0].contents[2].text
                        kind = table[pair_index].contents[day_index].contents[0].contents[3].contents[1]
                        group = table[pair_index].contents[day_index].contents[0].contents[3].contents[3]
                        weeks = table[pair_index].contents[day_index].contents[0].contents[4]
                        message += add_symbols('_', pair_number) + pair_phrase + '\n'
                        message += add_symbols('_', 'Недели: ') + weeks + '\n'
                        message += add_symbols('_', pair) + '\n'
                        message += add_symbols('_', 'Аудитория: ') + place + '\n'
                        message += add_symbols('_', 'Группа: ') + group + '\n'
                        message += kind + '\n\n'
                if 'Недели' in message:
                    return_message += message
                elif message != '':
                    return_message += message + 'Нет пар\n\n'
        else:
            return_message = 'Такого преподавателя не найдено, проверьте корректность введенных данных'
    else:
        return_message = 'Пришлите данные в формате /teacher Фамилия Имя Отчество'
    bot.sendMessage(chat_id=update.message.chat_id, text=return_message, parse_mode='markdown')


def changelog(bot, update):
    bot.sendMessage(chat_id=update.message.chat_id, text='Добавлена первая пробная версия расписания преподавателей.\n'
                                                         'Для использования отправьте /teacher Фамилия Имя Отчество' +
                                                         '(можно и просто фамилию или фамилия имя, но в случае совпадений будет выбран первый преподаватель)\n' +
                                                         'Позднее возможно добавлю поиск по неделям, сейчас недели просто указываются текстом')


def set_data(bot, update, args):
    text = 'Пожалуйста, пришлите данные в корректном формате, например: "/set ФИРТ БА-102М"'

    for i in range(len(args)):
        args[i] = ''.join(list(filter(lambda ch: ch not in leave, args[i].upper())))

    if len(args) == 2:
        if len(args[0]) > 15 or len(args[1]) > 21:
            bot.sendMessage(chat_id=update.message.chat_id,
                            text='Ты чо, шакал?')
            return
        elif '-' in args[1] and args[1].index('-') != len(args[1]) - 1:
            try:
                int(args[1].split('-')[1][0])
            except ValueError:
                bot.sendMessage(chat_id=update.message.chat_id,
                                text=text)
                return

            args.insert(1, args[1].split('-')[1][0])

            param = dict(csrfmiddlewaretoken=csrf, faculty=args[0], klass=args[1])

            head = {'Referer': URL,
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                    }

            req = requests.Request('POST', URL, headers=head, data=param, cookies=page.cookies).prepare()
            answer = client.send(req)

            for group in answer.json():
                if 'mane' in group and group['mane'] == args[2]:
                    args[2] = group['id']
                    chat_id = update.message.chat_id
                    red.hset(chat_id, 'faculty', args[0])
                    red.hset(chat_id, 'year', args[1])
                    red.hset(chat_id, 'group', args[2])
                    red.save()
                    bot.sendMessage(chat_id=chat_id,
                                    text="Спасибо, вы будете получать расписание для " +
                                         args[0] + ', ' +
                                         args[1] + ' курс, ' +
                                         group['mane'])
                    return
            text = 'Такой группы нет. ' + text
    bot.sendMessage(chat_id=update.message.chat_id,
                    text=text)


def add_symbols(symbol, text):
    return symbol + text + symbol


def setup(webhook_url=None):
    """If webhook_url is not passed, run with long-polling."""
    if webhook_url:
        bot = Bot(TOKEN)
        update_queue = Queue()
        dispatcher = Dispatcher(bot, update_queue)
    else:
        updater = Updater(TOKEN)
        bot = updater.bot
        dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler(str('start'), start))
    dispatcher.add_handler(CommandHandler(str('tomorrow'), tomorrow))
    dispatcher.add_handler(CommandHandler(str('today'), today))
    dispatcher.add_handler(CommandHandler(str('after'), after_tomorrow))
    dispatcher.add_handler(CommandHandler(str('exam'), exam))
    dispatcher.add_handler(CommandHandler(str('monday'), monday, pass_args=True))
    dispatcher.add_handler(CommandHandler(str('tuesday'), tuesday, pass_args=True))
    dispatcher.add_handler(CommandHandler(str('wednesday'), wednesday, pass_args=True))
    dispatcher.add_handler(CommandHandler(str('thursday'), thursday, pass_args=True))
    dispatcher.add_handler(CommandHandler(str('friday'), friday, pass_args=True))
    dispatcher.add_handler(CommandHandler(str('saturday'), saturday, pass_args=True))
    dispatcher.add_handler(CommandHandler(str('date'), on_date, pass_args=True))
    dispatcher.add_handler(CommandHandler(str('teacher'), teacher, pass_args=True))
    dispatcher.add_handler(CommandHandler(str('changelog'), changelog))
    dispatcher.add_handler(CommandHandler(str('set'), set_data, pass_args=True))

    if webhook_url:
        bot.set_webhook(webhook_url=webhook_url)
        logging.log(logging.INFO, 'im on a boat!')

        thread = Thread(target=dispatcher.start, name='dispatcher')
        thread.start()
        return update_queue, bot
    else:
        bot.set_webhook()
        logging.log(logging.INFO, 'im not on a boat, im sorry :c')
        updater.start_polling()
        updater.idle()


if __name__ == '__main__':
    setup()
