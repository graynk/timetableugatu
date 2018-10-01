#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals

from datetime import datetime, timedelta, date
from queue import Queue
from threading import Thread

#import botan
import logging
import pickle
import redis
import requests
import string
import sys
import threading
import time
from bs4 import BeautifulSoup, Tag
from pytz import timezone
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, Updater, CommandHandler, ConversationHandler, \
    CallbackQueryHandler, MessageHandler, Filters
from telegram.utils.promise import Promise

TOKEN = 'MY_TOKEN'
#BOTAN_TOKEN = 'BOTAN TOKEN' botan is shit tho and keeps on dying
logging.basicConfig(filename='/media/pi/ADATA HV620/log.txt',
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.INFO)
HOST = '127.0.0.1'
PORT = '6379'
PASS = 'REDIS_PASS'

MAIN, FAC, COURSE, GROUP, WEEK, OTHER, TEACHER, DATE = range(8)
facs_markup = None
course_markup = InlineKeyboardMarkup([
    [InlineKeyboardButton('Первый', callback_data='1'), InlineKeyboardButton('Второй', callback_data='2')],
    [InlineKeyboardButton('Третий', callback_data='3'), InlineKeyboardButton('Четвертый', callback_data='4')],
    [InlineKeyboardButton('Пятый', callback_data='5'), InlineKeyboardButton('Шестой', callback_data='6')]]
)
main_markup = InlineKeyboardMarkup([
    [InlineKeyboardButton('Сегодня', callback_data='/today'), InlineKeyboardButton('Завтра', callback_data='/tomorrow'),
     InlineKeyboardButton('Послезавтра', callback_data='/after')],
    [InlineKeyboardButton('Дни недели', callback_data='/week'), InlineKeyboardButton('Прочее', callback_data='/other')]
])
week_markup = InlineKeyboardMarkup([
    [InlineKeyboardButton('Понедельник', callback_data='/monday'),
     InlineKeyboardButton('Вторник', callback_data='/tuesday')],
    [InlineKeyboardButton('Среда', callback_data='/wednesday'),
     InlineKeyboardButton('Четверг', callback_data='/thursday')],
    [InlineKeyboardButton('Пятница', callback_data='/friday'),
     InlineKeyboardButton('Суббота', callback_data='/saturday')],
    [InlineKeyboardButton('Возврат в меню', callback_data='/main')]
])
other_markup = InlineKeyboardMarkup([
    [InlineKeyboardButton('Экзамены', callback_data='/exam'),
     InlineKeyboardButton('Преподаватели', callback_data='/teacher'),
     InlineKeyboardButton('На дату', callback_data='/date')],
    [InlineKeyboardButton('Изменения', callback_data='/changelog'),
     InlineKeyboardButton('Помощь', callback_data='/help')],
    [InlineKeyboardButton('Сброс группы', callback_data='/start')],
    [InlineKeyboardButton('Возврат в меню', callback_data='/main')]
])

logging.log(logging.INFO, 'here')
red = redis.Redis(host=HOST, port=PORT, db=0, password=PASS, decode_responses=True)
logging.log(logging.INFO, 'now here')
logging.log(logging.INFO, red.get('sem'))
leave = string.punctuation.replace(',', '').replace('-', ' ')
tz = timezone('Asia/Yekaterinburg')
URL = 'http://lk.ugatu.su/raspisanie/'
TEACHER_URL = 'http://lk.ugatu.su/teacher/#timetable'
client = requests.session()
page = client.get(URL, timeout=20)
logging.log(logging.INFO, 'got page')
teacher_page = client.get(TEACHER_URL)
logging.log(logging.INFO, 'got second page')
bs = BeautifulSoup(page.text, 'lxml')
teachbs = BeautifulSoup(teacher_page.text, 'lxml')

try:
    facs_keyboard = []
    facs = []
    for element in bs.findAll('select')[0]:
        if isinstance(element, Tag) and '-' not in element.text:
            facs.append(InlineKeyboardButton(element.text, callback_data=element.text))
    for fac in range(len(facs)):
        if fac % 2 == 0:
            facs_keyboard.append([facs[fac]])
        else:
            facs_keyboard[-1].append(facs[fac])
    facs_markup = InlineKeyboardMarkup(facs_keyboard)
    sem = bs.find(id='SemestrSchedule').contents[3]['value']
    logging.log(logging.INFO, sem)
    int(sem)
    red.set('sem', sem)
    week = bs.find('h3').next_sibling.next_sibling.contents[0].contents[0]
    logging.log(logging.INFO, week)
    int(week)
    red.set('week', week)
except ValueError:
    logging.log(logging.ERROR, 'and now im here what the fuck')
    red.set('sem', '4')
    red.set('week', '1')
todate = datetime.now(tz=tz).date()
red.set('current_date', str(todate))
red.set('current_day', str(todate.weekday()))


def find_week():
    global todate, week, page, bs
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
    message = 'Привет. Для того, чтобы начать работу с ботом, выберите свой факультет'
    bot.sendMessage(chat_id=update.message.chat_id, text=message, reply_markup=facs_markup)
    #botan.track(BOTAN_TOKEN, update.message.chat_id, {'Старт': 'Новый юзер или смена'}, 'Главное меню')
    return FAC


def course_choose(bot, update, user_data):
    query = update.callback_query
    chat_id = query.message.chat_id

    this_fac = query.data
    if this_fac == 'ИАТМ':
        this_fac = 'ФАТС'
    user_data['fac'] = this_fac

    bot.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text='Выбран факультет ' + this_fac + ', теперь выберите курс:'
    )

    bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=query.message.message_id,
        reply_markup=course_markup
    )
    return COURSE


def group_choose(bot, update, user_data):
    query = update.callback_query
    chat_id = query.message.chat_id
    year = query.data
    user_data['year'] = year
    param = dict(csrfmiddlewaretoken=page.cookies['csrftoken'], faculty=user_data['fac'], klass=year)

    head = {'Referer': URL,
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest'
            }

    req = requests.Request('POST', URL, headers=head, data=param, cookies=page.cookies).prepare()
    answer = client.send(req)

    group_keyboard = []
    groups = []
    for group in answer.json():
        if 'mane' in group:
            groups.append(InlineKeyboardButton(group['mane'], callback_data=group['mane'] + '|' + group['id']))
    if len(groups) == 0:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=query.message.message_id,
            text='Простите, но групп не найдено'
        )
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=query.message.message_id,
            reply_markup=None
        )
        return start(bot, update)
    for group in range(len(groups)):
        if group % 4 == 0:
            group_keyboard.append([groups[group]])
        else:
            group_keyboard[-1].append(groups[group])
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text='Выбран ' + year + ' курс, осталось выбрать группу:'
    )
    group_markup = InlineKeyboardMarkup(group_keyboard)
    bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=query.message.message_id,
        reply_markup=group_markup
    )
    return GROUP


def finish(bot, update, user_data):
    this_fac = user_data['fac']
    year = user_data['year']
    query = update.callback_query
    name, tg_id = query.data.split('|')
    chat_id = query.message.chat_id
    #botan.track(BOTAN_TOKEN, chat_id, {'Факультет': this_fac}, 'Инфа')
    #botan.track(BOTAN_TOKEN, chat_id, {'Группа': name}, 'Инфа')
    red.hset(chat_id, 'faculty', this_fac)
    red.hset(chat_id, 'year', year)
    red.hset(chat_id, 'group', tg_id)
    red.hdel(chat_id, 'd_buttons')
    red.save()
    bot.edit_message_text(chat_id=chat_id,
                          message_id=query.message.message_id,
                          parse_mode='markdown',
                          text="Спасибо, теперь вы можете получить расписание для " +
                               this_fac + ', ' +
                               year + ' курс, ' +
                               name +
                               '\nДля начала работы выберите необходимый пункт меню. '
                               'Расписание преподавателей, экзаменов и '
                               'помощь по боту находится в разделе *Прочее*. '
                               '\nБот поддерживает и работу с командами как альтернативу кнопочному меню, '
                               'чтобы получить весь список команды, отправьте /help ')
    bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=query.message.message_id,
        reply_markup=main_markup
    )
    return MAIN


def enable(bot, update):
    chat_id = update.message.chat_id
    red.hdel(chat_id, 'd_buttons')
    red.save()
    bot.sendMessage(chat_id, text='Готово, теперь вы снова будете видеть меню', reply_markup=main_markup)
    #botan.track(BOTAN_TOKEN, chat_id, {'Инлайн': 'Включен'}, 'Инфа')
    return MAIN


def disable(bot, update):
    chat_id = update.message.chat_id
    red.hset(chat_id, 'd_buttons', 'True')
    red.save()
    bot.sendMessage(chat_id,
                    text='Готово, теперь вы не будете видеть меню. Список команд можно узнать воспользовавшись /help')
    #botan.track(BOTAN_TOKEN, chat_id, {'Инлайн': 'Выключен'}, 'Инфа')


def main(bot, update):
    query = update.callback_query
    bot.edit_message_reply_markup(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        reply_markup=None
    )
    if query.data == '/today':
        today(bot, query)
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Расписание': 'Сегодня'}, 'Главное меню')
    elif query.data == '/tomorrow':
        tomorrow(bot, query)
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Расписание': 'Завтра'}, 'Главное меню')
    elif query.data == '/after':
        after_tomorrow(bot, query)
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Расписание': 'Послезавтра'}, 'Главное меню')
    elif query.data == '/week':
        if 'Выберите' in query.message.text or 'Спасибо,' in query.message.text:
            bot.edit_message_text(chat_id=query.message.chat_id,
                                  message_id=query.message.message_id,
                                  text='Выберите необходимый день недели')
            bot.edit_message_reply_markup(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                reply_markup=week_markup
            )
        else:
            bot.send_message(
                chat_id=query.message.chat_id,
                text='Выберите необходимый день недели',
                reply_markup=week_markup
            )
        return WEEK
    elif query.data == '/other':
        if 'Выберите' in query.message.text or 'Спасибо,' in query.message.text:
            bot.edit_message_reply_markup(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                reply_markup=other_markup
            )
        else:
            bot.send_message(
                chat_id=query.message.chat_id,
                text='Выберите необходимый пункт меню',
                reply_markup=other_markup
            )
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Переход': 'Настройки'}, 'Главное меню')
        return OTHER
    return MAIN


def show_week(bot, update):
    query = update.callback_query

    bot.edit_message_reply_markup(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        reply_markup=None
    )

    if query.data == '/monday':
        monday(bot, query, [])
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Неделя': 'Понедельник'}, 'Неделя')
    elif query.data == '/tuesday':
        tuesday(bot, query, [])
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Неделя': 'Вторник'}, 'Неделя')
    elif query.data == '/wednesday':
        wednesday(bot, query, [])
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Неделя': 'Среда'}, 'Неделя')
    elif query.data == '/thursday':
        thursday(bot, query, [])
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Неделя': 'Четверг'}, 'Неделя')
    elif query.data == '/friday':
        friday(bot, query, [])
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Неделя': 'Пятница'}, 'Неделя')
    elif query.data == '/saturday':
        saturday(bot, query, [])
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Неделя': 'Суббота'}, 'Неделя')
    elif query.data == '/main':
        bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text='Выберите необходимый пункт меню'
        )
        bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=main_markup
        )
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Другое': 'Возврат в меню'}, 'Неделя')
    return MAIN


def show_other(bot, update):
    query = update.callback_query

    bot.edit_message_reply_markup(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        reply_markup=None
    )

    if query.data == '/start':
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Выбор': 'Сброс'}, 'Другое')
        return start(bot, query)
    elif query.data == '/exam':
        exam(bot, query)
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Выбор': 'Экзамен'}, 'Другое')
    elif query.data == '/teacher':
        bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text='Пожалуйста пришлите ФИО преподавателя или напишите "Возврат", чтобы вернуться в главное меню'
        )
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Выбор': 'Препод'}, 'Другое')
        return TEACHER
    elif query.data == '/date':
        bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text='Пожалуйста пришлите дату в формате "день месяц" (например 5 9 это пятое сентября) или напишите '
                 '"Возврат", чтобы вернуться в главное меню',
            parse_mode='markdown'
        )
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Выбор': 'Дата'}, 'Другое')
        return DATE
    elif query.data == '/changelog':
        changelog(bot, query)
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Выбор': 'Чейнджлог'}, 'Другое')
    elif query.data == '/help':
        help_me(bot, query)
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Выбор': 'Помощь'}, 'Другое')
    elif query.data == '/main':
        bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=main_markup
        )
        #botan.track(BOTAN_TOKEN, update.callback_query.message.chat_id, {'Выбор': 'Возврат в меню'}, 'Другое')
    return MAIN


def help_me(bot, update):
    message = 'С последним обновлением я перенес весь интерфейс бота на кнопочное меню, но на случай, ' \
              'если я где-то накосячил и все поломалось, вы все еще можете использовать старые команды ' \
              '(если я и их не сломал. ' \
              'Как обычно, если что -- пинайте @semifunctional). Чтобы выключить меню, отправьте /disable. ' \
              'Чтобы включить -- /enable' \
              '\nИспользуйте одну из следующих команд для получения расписания на:\n' \
              '/today - сегодня\n' \
              '/tomorrow - завтра\n' \
              '/after - послезавтра\n' \
              '/monday - понедельник\n' \
              '/tuesday - вторник\n' \
              '/wednesday - среда\n' \
              '/thursday - четверг\n' \
              '/friday - пятница\n' \
              '/saturday - суббота\n' \
              '/date день месяц - расписание на конкретный день, например "/date 1 3" ' \
              'это расписание на первое марта\n' \
              '/exam - расписание экзаменов\n' \
              '/teacher Фамилия Имя Отчество - расписание преподавателя (тестовая версия). Вводить можно и только ' \
              'Фамилия Имя, ' \
              'или только Имя Отчество или вообще что-то одно, но вернется по первому совпадению.\n' + \
              '/changelog - последнее нововведение\n' + \
              'К каждой из команд, относящихся к дням недели можно добавить номер недели, ' \
              'например "/monday 5" вернет ' \
              'расписание на понедельник пятой недели. ' \
              'По умолчанию возвращается расписание на ближайший будущий день недели.' + \
              'Чтобы сменить группу, отправьте команду /start или же команду:\n' + \
              '/set факультет группа, например "/set ФИРТ БА-102М"\n'
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    bot.sendMessage(chat_id=update.message.chat_id, text=message, reply_markup=reply_markup)
    return MAIN


def exam(bot, update):
    chat_id = update.message.chat_id
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    if not (red.hexists(chat_id, 'faculty') and red.hexists(chat_id, 'year') and red.hexists(chat_id, 'group')):
        bot.sendMessage(chat_id=update.message.chat_id, text='Сначала используйте команду "/set факультет группа"',
                        parse_mode='markdown', reply_markup=reply_markup)
        return
    faculty = red.hget(chat_id, 'faculty')
    year = red.hget(chat_id, 'year')
    groupname = red.hget(chat_id, 'group')
    param = dict(csrfmiddlewaretoken=page.cookies['csrftoken'], faculty=faculty, klass=year)

    return_message = ''

    param['ScheduleType'] = 'Экзамены'
    param['group'] = groupname
    param['sem'] = sem
    param['view'] = 'ПОКАЗАТЬ'
    answer = client.post(URL, param)

    bs_exam = BeautifulSoup(answer.text, 'lxml')

    for row in bs_exam.findAll('tr'):
        if len(row.contents) == 2 and row.find_all('font'):
            found = row.find_all('font')
            lec_time = '_' + found[0].text + '_\n'
            lec_date = '*' + row.find_all('p')[0].contents[2] + '*\n'
            title = '*' + found[1].text + '*\n'
            place = '_Аудитория:_ ' + found[2].text + '\n'
            kind = found[3].contents[0].text + '\n'
            if (len(found[3].contents)) >= 2:
                lec_teacher = found[3].contents[1].text + '\n\n'
            else:
                lec_teacher = '\n'
            return_message += title + lec_date + lec_time + place + kind + lec_teacher
    if return_message == '':
        return_message = 'Расписание отсутствует'
    bot.sendMessage(chat_id=update.message.chat_id, text=return_message, parse_mode='markdown',
                    reply_markup=reply_markup)

    return MAIN


def get_table(tg_id, deltaday, needed_week, needed_date):
    if not (red.hexists(tg_id, 'faculty') and red.hexists(tg_id, 'year') and red.hexists(tg_id, 'group')):
        return 'Сначала используйте команду "/set факультет группа"'
    faculty = red.hget(tg_id, 'faculty')
    year = red.hget(tg_id, 'year')
    groupname = red.hget(tg_id, 'group')
    # короче после последнего изменения сайта я рассчитываю на то, что dict упорядоченный
    param = dict(csrfmiddlewaretoken=page.cookies['csrftoken'], faculty=faculty, klass=year)

    return_message = ''
    param['group'] = groupname
    param['ScheduleType'] = 'На дату'
    param['week'] = '1'
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
    day = "{0:0=2d}".format(needed_date.day)
    month = str(needed_date.month)
    year = str(needed_date.year)
    dotdate = day + '.' + month + '.' + year
    dashdate = year + '-' + month + '-' + day
    param['date'] = dashdate
    param['sem'] = sem
    param['view'] = 'ПОКАЗАТЬ'
    startt = time.time()
    #answer = client.post(URL, param)
    head = {'Host': 'lk.ugatu.su','User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:61.0) Gecko/20100101 Firefox/61.0',
'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
'Accept-Language': 'en-GB,en;q=0.5',
'Accept-Encoding': 'gzip, deflate, br',
'Referer': 'https://lk.ugatu.su/raspisanie/',
'Content-Type': 'application/x-www-form-urlencoded',
'DNT': '1',
'Connection': 'keep-alive',
'Upgrade-Insecure-Requests': '1'}

    req = requests.Request('POST', URL, headers=head, data=param, cookies=page.cookies).prepare()
    answer = client.send(req)    logging.log(logging.INFO, 'final request ' + str(time.time() - startt))
    beas = BeautifulSoup(answer.text, 'lxml')
    message_list = []
    for row in beas.findAll('td'):
        if len(row.contents) == 1 and len(row.contents[0]) > 4:
            # заголовок
            message_list.append('*' + row.text + ', ' + dotdate + '\n' + current_week + ' неделя*\n\n')
        elif row.find('div') and row.find('div').has_attr('class') and row.find('div')['class'][0] == 'font-couple':
            # номер пары
            class_info = row.find_all('div')
            message_list.append('_' + class_info[0].text + ':_ ' + class_info[1].text + '\n')
        elif row.find('font'):
            # информация о паре
            name = ''
            room = ''
            teacher_name = ''
            kind = ''
            all_info = row.find_all('font')
            split = '\n\n'
            for font in all_info:
                if not font.has_attr('class'):
                    continue
                if font['class'][0] == 'font-subject':
                    if name != '':
                        message_list.append(name + '\n' +
                                            room + '\n' +
                                            teacher_name +
                                            kind + split)
                    name = font.text
                elif font['class'][0] == 'font-classroom':
                    room = '_Аудитория:_ ' + font.text
                elif font['class'][0] == 'font-teacher':
                    teacher_name = ''
                    kind = ''
                    teachers = []
                    for tag in font.contents:
                        if tag.find('font'):
                            continue
                        elif tag.name == 'p':
                            kind = tag.text
                        else:
                            teachers.append(tag.contents[0])

                    if len(teachers) != 0:
                        teacher_name = '_Преподаватель_: ' + ', '.join(teach for teach in teachers)
                        kind = '\n' + kind
                    index = all_info.index(font)
                    if index + 1 != len(all_info):
                        split = '\n---\n'
                    else:
                        split = '\n\n'

            message_list.append(name + '\n' +
                                room + '\n' +
                                teacher_name +
                                kind + split)

    for message in message_list:
        index = message_list.index(message)
        if not ('пара:' in message and (index == len(message_list) - 1 or 'пара:' in message_list[index + 1])):
            return_message += message
    if return_message == '':
        return_message = 'Пар нет'
    return return_message


def today(bot, update):
    message = get_table(update.message.chat_id, 0, -1, None)
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode='markdown', reply_markup=reply_markup)
    return MAIN


def tomorrow(bot, update):
    message = get_table(update.message.chat_id, 1, -1, None)
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode='markdown', reply_markup=reply_markup)
    return MAIN


def after_tomorrow(bot, update):
    message = get_table(update.message.chat_id, 2, -1, None)
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode='markdown', reply_markup=reply_markup)
    return MAIN


def monday(bot, update, args):
    return for_day(bot, update, 0, args)


def tuesday(bot, update, args):
    return for_day(bot, update, 1, args)


def wednesday(bot, update, args):
    return for_day(bot, update, 2, args)


def thursday(bot, update, args):
    return for_day(bot, update, 3, args)


def friday(bot, update, args):
    return for_day(bot, update, 4, args)


def saturday(bot, update, args):
    return for_day(bot, update, 5, args)


def for_day(bot, update, daynumber, args):
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    needed_week = -1
    temp_message = ''
    if len(args) != 0:
        if len(args[0]) > 2:
            bot.sendMessage(chat_id=update.message.chat_id, text='Ты чо, шакал?', reply_markup=reply_markup)
        try:
            needed_week = int(args[0])
        except ValueError:
            temp_message = 'Ну нельзя же так, ну чего ты. Ну просили же цифры. На вот как обычно, раз так \n\n'

    current = datetime.now(tz=tz).weekday()
    if daynumber < current and len(args) == 0:
        daynumber += 7
        needed_week = -2
    message = get_table(update.message.chat_id, daynumber - current, needed_week, None)
    bot.sendMessage(chat_id=update.message.chat_id, text=temp_message + message, parse_mode='markdown',
                    reply_markup=reply_markup)
    return MAIN


def buttoned_date(bot, update):
    if update.message.text.lower() == 'возврат':
        bot.sendMessage(chat_id=update.message.chat_id, text='Выберите необходимый пункт меню',
                        reply_markup=main_markup)
    else:
        on_date(bot, update, update.message.text.split(' '))
    return MAIN


def on_date(bot, update, args):
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    if len(args) != 2 or len(args[0]) > 2 or len(args[1]) > 2:
        bot.sendMessage(chat_id=update.message.chat_id,
                        text='Пожалуйста, пришлите данные в корректном формате, например "/date 1 3"',
                        reply_markup=reply_markup)
        return
    try:
        day = int(args[0])
        month = int(args[1])
    except ValueError:
        bot.sendMessage(chat_id=update.message.chat_id,
                        text='Пожалуйста, пришлите данные в корректном формате, например "/date 1 3"',
                        reply_markup=reply_markup)
        return
    now = datetime.now(tz=tz).date()
    needed = date(year=now.year, month=month, day=day)
    message = get_table(update.message.chat_id, needed.weekday(), -1, needed)
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode='markdown', reply_markup=reply_markup)
    return MAIN


def buttoned_teacher(bot, update):
    if update.message.text.lower() == 'возврат':
        bot.sendMessage(chat_id=update.message.chat_id, text='Выберите необходимый пункт меню',
                        reply_markup=main_markup)
    else:
        teacher(bot, update, update.message.text.split(' '))
    return MAIN


def teacher(bot, update, args):
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
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
            param = dict(chair='', csrfmiddlewaretoken=csrf, date=red.get('current_date'), ScheduleType='За семестр',
                         sem=red.get('sem'), teacher=teacher_number, view='ПОКАЗАТЬ', week=find_week())
            answer = client.post(TEACHER_URL, param)
            beas = BeautifulSoup(answer.text, 'lxml')
            if 'Расписание отсутствует' in answer.text or len(beas.findAll('tr')) == 0:
                bot.sendMessage(chat_id=update.message.chat_id, text='Расписание отсутствует.',
                                reply_markup=reply_markup)
                return
            return_message += add_symbols('*', find_week() + ' неделя\n')
            return_message += add_symbols('*', teacher_name) + '\n\n'
            for day_index in range(3, 14, 2):
                table = beas.findAll('tr')
                message = add_symbols('*', table[0].contents[day_index].text) + '\n'
                for pair_index in range(1, 7):
                    count_subpairs = len(table[pair_index].contents[day_index].contents)
                    if count_subpairs > 0:
                        pair_number = table[pair_index].findAll('div')[0].text + ': '
                        pair_phrase = table[pair_index].findAll('div')[1].text
                        message += add_symbols('_', pair_number) + pair_phrase + '\n'
                        for subpair in range(0, count_subpairs, 2):
                            font = table[pair_index].contents[day_index].contents[subpair].findAll('font')
                            pair = font[0].text
                            place = font[1].text
                            kind = font[2].find('p').text
                            group = font[2].find('a').text
                            weeks = table[pair_index].contents[day_index].contents[subpair+1].text
                            divider = '\n\n' if count_subpairs - 2 == subpair else '\n---\n'
                            message += add_symbols('_', 'Недели: ') + weeks + '\n'
                            message += add_symbols('_', pair) + '\n'
                            message += add_symbols('_', 'Аудитория: ') + place + '\n'
                            message += add_symbols('_', 'Группа: ') + group + '\n'
                            message += kind + divider
                if 'Недели' in message:
                    return_message += message
                elif message != '':
                    return_message += message + 'Нет пар\n\n'
        else:
            return_message = 'Такого преподавателя не найдено, проверьте корректность введенных данных'
    else:
        return_message = 'Пришлите данные в формате /teacher Фамилия Имя Отчество'
    bot.sendMessage(chat_id=update.message.chat_id, text=return_message, parse_mode='markdown',
                    reply_markup=reply_markup)
    return MAIN


def changelog(bot, update):
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    bot.sendMessage(chat_id=update.message.chat_id,
                    text='Переписалп парсер. По невнимательности могут быть косяки, '
                         'но надеюсь будет устойчивей к поломкам в целом.\n'
                         '\n---\nВвел кнопочное меню, надеюсь ничего не поломалось, хотя это вряд ли.'
                         ' Если нашли что-то корявое, то пишите @semifunctional. '
                         'А если не нашли, то СТАВЬ ЛАЙК НА КАНАЛ ПОДПИСЫВАЙСЯ ДРУЗЬЯМ РАССКАЖИ'
                         '\nКроме того, оказывается на сайте добавили расписание в XML, '
                         'но пока что я все равно буду через пень-колоду парсить HTML, '
                         'потому что конечно же они всю информацию о паре подряд в одну клетку сваливают'
                         '\n---\nБот перенесен с Openshift на мою домашнюю RPI (пока что без вебхука), '
                         'должно существенно уменьшиться время ответа'
                         '\n---\nДобавлена первая пробная версия расписания преподавателей.\n'
                         'Для использования отправьте /teacher Фамилия Имя Отчество'
                         '(можно и просто фамилию или фамилия имя, '
                         'но в случае совпадений будет выбран первый преподаватель)\n'
                         'Позднее возможно добавлю поиск по неделям, сейчас недели просто указываются текстом\n',
                    reply_markup=reply_markup)
    return MAIN


def set_data(bot, update, args):
    reply_markup = main_markup if not red.hget(update.message.chat_id, 'd_buttons') else None
    text = 'Пожалуйста, пришлите данные в корректном формате, например: "/set ФИРТ БА-102М"'

    for i in range(len(args)):
        args[i] = ''.join(list(filter(lambda ch: ch not in leave, args[i].upper())))

    if len(args) == 2:
        if len(args[0]) > 15 or len(args[1]) > 21:
            bot.sendMessage(chat_id=update.message.chat_id,
                            text='Ты чо, шакал?', reply_markup=reply_markup)
            return
        elif '-' in args[1] and args[1].index('-') != len(args[1]) - 1:
            try:
                int(args[1].split('-')[1][0])
            except ValueError:
                bot.sendMessage(chat_id=update.message.chat_id,
                                text=text, reply_markup=reply_markup)
                return

            args.insert(1, args[1].split('-')[1][0])

            if args[0] == 'ИАТМ':
                args[0] = 'ФАТС'

            param = dict(csrfmiddlewaretoken=page.cookies['csrftoken'], faculty=args[0], klass=args[1])

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
                                         group['mane'], reply_markup=reply_markup)
                    return
            text = 'Такой группы нет. ' + text
    bot.sendMessage(chat_id=update.message.chat_id,
                    text=text, reply_markup=reply_markup)
    return MAIN


def add_symbols(symbol, text):
    return symbol + text + symbol


def count(bot, update):
    if update.message.chat_id == int('ADMIN_TELEGRAM_ID'): # obviously should be done with Filters, 'twas a long time ago tho
        bot.sendMessage(update.message.chat_id, text=red.info("Keyspace")['db0']['keys'])


def setup(webhook_url=None):
    """If webhook_url is not passed, run with long-polling."""
    updater = Updater(TOKEN)
    bot = updater.bot
    dispatcher = updater.dispatcher

    # dispatcher.add_handler(CommandHandler(str('start'), start))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CommandHandler('enable', enable),
                      CommandHandler(str('today'), today),
                      CommandHandler(str('tomorrow'), tomorrow),
                      CommandHandler(str('after'), after_tomorrow),
                      CommandHandler(str('exam'), exam),
                      CommandHandler(str('monday'), monday, pass_args=True),
                      CommandHandler(str('tuesday'), tuesday, pass_args=True),
                      CommandHandler(str('wednesday'), wednesday, pass_args=True),
                      CommandHandler(str('thursday'), thursday, pass_args=True),
                      CommandHandler(str('friday'), friday, pass_args=True),
                      CommandHandler(str('saturday'), saturday, pass_args=True),
                      CommandHandler(str('date'), on_date, pass_args=True),
                      CommandHandler(str('teacher'), teacher, pass_args=True),
                      CommandHandler(str('changelog'), changelog),
                      CommandHandler(str('help'), help_me),
                      # CommandHandler(str('enable'), enable),
                      CommandHandler(str('disable'), disable),
                      CommandHandler(str('set'), set_data, pass_args=True)
                      ],
        states={
            FAC: [CallbackQueryHandler(course_choose, pass_user_data=True)],
            COURSE: [CallbackQueryHandler(group_choose, pass_user_data=True)],
            GROUP: [CallbackQueryHandler(finish, pass_user_data=True)],
            MAIN: [CallbackQueryHandler(main)],
            WEEK: [CallbackQueryHandler(show_week)],
            OTHER: [CallbackQueryHandler(show_other)],
            TEACHER: [MessageHandler(Filters.text, buttoned_teacher)],
            DATE: [MessageHandler(Filters.text, buttoned_date)]
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler('count', count))

    def load_data():
        try:
            f = open('backup/conversations', 'rb')
            conv_handler.conversations = pickle.load(f)
            f.close()
            f = open('backup/userdata', 'rb')
            dispatcher.user_data = pickle.load(f)
            f.close()
        except FileNotFoundError:
            logging.error("Data file not found")

    # noinspection PyBroadException
    def save_data():
        while True:
            time.sleep(3600)
            # Before pickling
            resolved = dict()
            for k, v in conv_handler.conversations.items():
                if isinstance(v, tuple) and len(v) is 2 and isinstance(v[1], Promise):
                    # noinspection PyBroadException
                    try:
                        new_state = v[1].result()  # Result of async function
                    except:
                        new_state = v[0]  # In case async function raised an error, fallback to old state
                    resolved[k] = new_state
                else:
                    resolved[k] = v
            try:
                f = open('backup/conversations', 'wb+')
                pickle.dump(resolved, f)
                f.close()
                f = open('backup/userdata', 'wb+')
                pickle.dump(dispatcher.user_data, f)
                f.close()
            except:
                logging.error(sys.exc_info()[0])

    load_data()
    threading.Thread(target=save_data).start()

    if webhook_url:
        updater.start_webhook(listen='0.0.0.0',
                              port=8443,
                              url_path=TOKEN,
                              key='private.key',
                              cert='cert.pem',
                              webhook_url='URL' + TOKEN)
        logging.log(logging.INFO, 'im on a boat!')

#        thread = Thread(target=dispatcher.start, name='dispatcher')
 #       thread.start()
#        return update_queue, bot
    else:
        print('again, no webhook')
        bot.set_webhook('')
        logging.log(logging.INFO, 'im not on a boat, im sorry :c')
        updater.start_polling()
        updater.idle()


if __name__ == '__main__':
    setup('')
