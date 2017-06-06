# !/usr/bin/env python
# coding: utf8

import apiclient.discovery
import BaseHTTPServer
import contextlib
import oauth2client.service_account
import httplib2
import HTMLParser
import json
import logging
import os
import pycountry
import random
import requests
import socket
import SocketServer
import sys
import threading
import time
import urllib
import urlparse

DEFAULT_HTTP_PORT = 52000
JSON_FILE = 'GooglePlayCustomerService-ae3d674c4880.json'
PACKAGE_LIST = [
    'com.senspark.shootdinosaureggs2',
    'com.senspark.goldminerclassic',
    'com.senspark.android.southernthirteen',
    'com.senspark.goldminerclassicorigin',
    'com.senspark.android.phom',
    'us.can0p.shootdinosaureggs',
]

class Config:
    __data = None

    @classmethod
    def get_current_dir(cls):
        return os.path.dirname(os.path.realpath(__file__))

    @classmethod
    def get_config_path(cls):
        return os.path.join(cls.get_current_dir(), 'config.json')

    @classmethod
    def __create_config_file_if_not_exist(cls):
        path = cls.get_config_path()
        if not os.path.exists(path):
            with open(path, 'w') as ignored_file:
                ignored = 1

    @classmethod
    def __get_dict(cls, data, key):
        if data.get(key) == None:
            data[key] = {}
        return data[key]

    @classmethod
    def __get_array(cls, data, key):
        if data.get(key) == None:
            data[key] = []
        return data[key]

    @classmethod
    def __append_unique(cls, lst, val):
        if val not in lst:
            lst.append(val)

    def __lazy_read_config_data(self):
        if self.__data == None:
            self.read_config_data()

    def read_config_data(self):
        Config.__create_config_file_if_not_exist()
        with open(Config.get_config_path(), 'r') as input_file:
            try:
                self.__data = json.load(input_file)
            except ValueError:
                self.__data = {}

    def write_config_data(self):
        if self.__data != None:
            with open(Config.get_config_path(), 'w') as output_file:
                json.dump(self.__data, output_file)

    def __get_auto_time_point_object(self):
        self.__lazy_read_config_data()
        return Config.__get_dict(self.__data, 'auto')

    def __get_manual_time_point_object(self):
        self.__lazy_read_config_data()
        return Config.__get_dict(self.__data, 'manual')

    def get_auto_time_point(self, package_name):
        return self.__get_auto_time_point_object().get(package_name, 0)

    def get_manual_time_point(self, package_name):
        return self.__get_manual_time_point_object().get(package_name, 0)

    def set_auto_time_point(self, package_name, time_point):
        self.__lazy_read_config_data()
        self.__get_auto_time_point_object()[package_name] = time_point
        self.write_config_data()

    def set_manual_time_point(self, package_name, time_point):
        self.__lazy_read_config_data()
        self.__get_manual_time_point_object()[package_name] = time_point
        self.write_config_data()

    def __get_settings_object(self):
        self.__lazy_read_config_data()
        return Config.__get_dict(self.__data, 'settings')

    def get_http_port(self):
        return self.__get_settings_object().get('port', DEFAULT_HTTP_PORT)

    def get_package_list(self):
        settings = self.__get_settings_object()
        return Config.__get_array(settings, 'packages')

    def add_package(self, package_name):
        Config.__append_unique(self.get_package_list(), package_name)
        self.write_config_data()

class Command:
    __params = None
    __callback = None

    def __init__(self, signature, callback):
        self.__params = signature.split(' ')
        self.__callback = callback

    def execute(self, params):
        if len(self.__params) != len(params):
            return False

        i = 0
        placeholders = []
        while i < len(params):
            __param = self.__params[i]
            param = params[i]

            if __param == param:
                # Matched.
                i = i + 1
                continue

            if __params == '%s':
                # Expect a string.
                placeholders.append(params)
                i = i + 1
                continue

            if __params == '%d':
                # Expect an integer.
                if not params.isdigit():
                    return False

                placeholders.append(params)
                i = i + 1
                continue

            # Not matched.
            return False

        self.__callback(*placeholders)
        return True

class Review:
    __review = None

    # Initializes the review wrapper with the specified review.
    def __init__(self, review):
        self.__review = review

    # Gets the author's name.
    # Nullable.
    def get_author_name(self):
        return self.__review.get('authorName', None)

    # Gets the review ID.
    def get_review_id(self):
        return self.__review['reviewId']

    def __get_user_comment_object(self):
        return self.__review['comments'][0]['userComment']

    # Gets the user's comment, including title and body text separated by a tab character.
    def get_user_comment(self):
        return self.__get_user_comment_object()['text']

    # Gets the user's comment as a tuple of title text and body text.
    def get_user_comment_split(self):
        return split_comment(self.get_user_comment())

    # Gets the review's application version, including version name and version code.
    def get_app_version(self):
        app_version_code = self.__get_user_comment_object().get('appVersionCode', None)
        app_version_name = self.__get_user_comment_object().get('appVersionName', None)

        if app_version_code == None:
            return None
        return 'v%s (%s)' % (app_version_name, app_version_code)

    def __get_reviewer_language(self):
        return self.__get_user_comment_object()['reviewerLanguage']

    # Gets the reviewer's country.
    def get_user_country(self):
        language_code, country_code = self.__get_reviewer_language().split('_')
        country_name = pycountry.countries.get(alpha_2=country_code).name
        return country_name

    def get_user_last_modified(self):
        return self.__get_user_comment_object()['lastModified']['seconds']

    def get_star_rating(self):
        return self.__get_user_comment_object()['starRating']

    def get_star_repr(self):
        return parse_stars(self.__get_star_rating())

    def get_color(self):
        return color_for_stars(self.__get_star_rating())

    def __create_user_callback_id(self, package_name):
        return create_callback_id(self.get_review_id(), package_name, 'user')

    def __create_developer_callback_id(self, package_name):
        return create_callback_id(self.get_review_id(), package_name, 'developer')

    def has_developer_comment(self):
        return len(self.__review['comments']) == 2

    def __get_developer_comment_object(self):
        if not self.has_developer_comment():
            return None

        return self.__review['comments'][1]['developerComment']

    def get_developer_comment(self):
        if not self.has_developer_comment():
            return None

        return self.__get_developer_comment_object()['text']

    def get_developer_last_modified(self):
        if not self.has_developer_comment():
            return 0

        return self.__get_developer_comment_object()['lastModified']['seconds']

    # Sample:
    # Author · Viet Name
    # ★★★★☆
    # this is my comment
    # v1.0.1 (1111) | May 31, 2017 at 9:59 AM
    # @param review The review information retrieved from androidpublisher.
    # @return A formatted dictionary.
    def format_user_comment(self, package_name):
        attachment = {}
        attachment['title']         = self.get_star_repr()
        attachment['ts']            = self.get_user_last_modified()
        attachment['color']         = self.get_color()
        attachment['mrkdwn_in']     = ['text']
        attachment['callback_id']   = self.__create_user_callback_id(package_name)

        # https://api.slack.com/docs/message-attachments
        comment_title, comment_body = self.get_user_comment_split()
        attachment['fields'] = [{
            'title': comment_title,
            'value': comment_body,
            'short': True
        }]

        # Header.
        author_texts = []

        # User's name.
        if author_name != None and len(author_name) > 0:
            author_texts.append(author_name)

        # User's country.
        author_texts.append(country_name)

        attachment['author_name'] = u' · '.join(author_texts)

        # Footer.
        footer_texts = []

        # Package name.
        footer_texts.append(package_name)

        # Store link.
        footer_texts.append('<%s|Store Link>' % get_store_link(package_name))

        # Use Google Translation.
        google_translation_link = get_google_translation_link('auto', 'en', self.get_user_comment())
        footer_texts.append('<%s|Google Translation>' % google_translation_link)

        # App version code and version name.    
        if self.get_app_version() != None:
            footer_texts.append(self.get_app_version())

        attachment['footer'] = u' · '.join(footer_texts)

        # Buttons.
        attachment['actions'] = []

        return attachment

    def format_developer_comment(self, package_name):
        if not self.has_developer_comment():
            return None

        attachment = {}
        attachment['title']         = 'Reply'
        attachment['text']          = self.get_developer_comment()
        attachment['ts']            = self.get_developer_last_modified()
        attachment['color']         = self.get_color()
        attachment['mrkdwn_in']     = ['text']
        attachment['callback_id']   = self.__create_developer_callback_id(package_name)

        return attachment

# Gets the Google Play Store app link.
# @param package_name The package name of the application.
# @return The URL link to store.
def get_store_link(package_name):
    return 'https://play.google.com/store/apps/details?id=%s' % package_name

# https://webapps.stackexchange.com/questions/12125/how-to-get-a-link-to-a-google-translate-translation
def get_google_translation_link(original_language, destination_language, text):
    return 'http://translate.google.com/#%s/%s/%s' % (original_language, destination_language, urllib.quote_plus(text))

# Attempts to read the HTML source.
# @param url The URL to the source.
# @return HTML source.
def read_source(url):
    return urllib.urlopen(url).read()

# Gets the cover image URL within the HTML source.
# @param source The HTML source.
# @return Cover image URL.
def get_cover_image_url(source):
    i = source.find('"cover-image" src="')
    if i == -1:
        return None

    # Skip to the first ".
    i += 19

    j = source.find('"', i)
    if j == -1:
        return None

    # Skip =w300
    j -= 4

    # Substring.
    result = source[i:j]

    # Add `https:`
    # Add `=w16`: indicate 16x16 pixels resolution.
    result = 'https:%sw16' % result
    return result

# Converts from star count to text.
# @param star_count The number of stars
# @return String.
def parse_stars(star_count):
    stars = {}
    stars[1] = u'★☆☆☆☆'
    stars[2] = u'★★☆☆☆'
    stars[3] = u'★★★☆☆'
    stars[4] = u'★★★★☆'
    stars[5] = u'★★★★★'
    return stars[star_count]

# Converts from star count to color.
# @param star_count The number of stars.
# @return Color in hex format.
def color_for_stars(star_count):
    colors = {}
    colors[1] = '#ffdddd'
    colors[2] = '#eebbbb'
    colors[3] = '#dd8888'
    colors[4] = '#cc4444'
    colors[5] = '#880000'
    return colors[star_count]

def split_comment(comment):
    title, body = comment.split('\t', 1)
    return title, body

# Convert seconds to text.
# Sample: May 31, 2017 at 9:59 AM.
def parse_time_point(seconds_since_epoch):
    # https://stackoverflow.com/questions/12400256/python-converting-epoch-time-into-the-datetime
    # http://strftime.org/
    return time.strftime("%b %-d, %Y at %-I:%M %p", time.gmtime(int(seconds_since_epoch)))

# https://stackoverflow.com/questions/4548684/how-to-get-the-seconds-since-epoch-from-the-time-date-output-of-gmtime-in-py
def get_seconds_since_epoch():
    return int(time.time())

# https://developers.google.com/android-publisher/api-ref/reviews/reply
# https://developers.google.com/apis-explorer/#p/androidpublisher/v2/androidpublisher.reviews.reply
# @param package_name The application package name.
# @param review_id The ID of the review.
# @param reply_text The comment.
def reply_review(service, package_name, review_id, reply_text):
    return service.reviews().reply(
               packageName=package_name,
               reviewId=review_id,
               body={'replyText': reply_text}
           ).execute()


def create_callback_id(review_id, package_name, tag):
    return '|'.join([review_id, package_name, tag])

def parse_callback_id(callback_id):
    review_id, package_name, tag = callback_id.split('|')
    return review_id, package_name, tag

def add_translate_button(attachment):
    # Translate (to English) button.
    translate_button = {}
    translate_button['name'] = 'translate'
    translate_button['text'] = 'Translate to English'
    translate_button['type'] = 'button'

    attachment['actions'].append(translate_button)

def remove_translate_button(attachment):
    attachment['actions'] = [action for action in attachment['actions'] if action['name'] != 'translate']

def add_reply_button(attachment):
    reply_button = {}
    reply_button['name'] = 'reply'
    reply_button['text'] = 'Reply'
    reply_button['type'] = 'select'
    reply_button['data_source'] = 'external'
    reply_button['min_query_length'] = 2

    attachment['actions'].append(reply_button)

def handle_translate_button(review_id, package_name, original_attachments, service):
    # Translate button.
    __review = service.reviews().get(
        packageName=package_name, 
        reviewId=review_id,
        translationLanguage='en_US'
    ).execute()

    review = Review(__review)

    user_callback_id = create_callback_id(review_id, package_name, 'user')
    comment_title, comment_body = review.get_user_comment_split()

    attachments = []
    for original_attachment in original_attachments:
        if original_attachment['callback_id'] == user_callback_id:
            original_attachment['fields'].append({
                'title': comment_title,
                'value': comment_body,
                'short': True
            })
            remove_translate_button(original_attachment)
        attachments.append(original_attachment)

    return attachments

def handle_reply_button(review_id, package_name, original_attachments, service, text):
    # Reply the typed text.
    result = reply_review(service, package_name, review_id, text)
    reply_text = result['result']['replyText']
    last_edited = result['result']['lastEdited']['seconds']

    attachments = []

    user_callback_id = create_callback_id(review_id, package_name, 'user')
    callback_id = create_callback_id(review_id, package_name, 'developer')

    # Remove existing (dev) attachment.
    temp_attachments = [attachment for attachment in original_attachments if attachment['callback_id'] != callback_id]

    # Add new (dev) attachment.
    for original_attachment in temp_attachments:
        attachments.append(original_attachment)
        if original_attachment['callback_id'] == user_callback_id:
            attachment = {}
            attachment['title']         = 'Reply'
            attachment['text']          = reply_text
            attachment['ts']            = last_edited
            attachment['color']         = original_attachment['color']
            attachment['mrkdwn_in']     = ['text']
            attachment['callback_id']   = callback_id
            attachments.append(attachment)

    return attachments

def handle_message_button(params, response, service):
    original_message    = params['original_message']
    attachment_id       = params['attachment_id']
    callback_id         = params['callback_id']
    response_url        = params['response_url']
    actions             = params['actions']

    review_id, package_name, tag = parse_callback_id(callback_id)

    action              = actions[0]
    action_type         = action['type']
    action_name         = action['name']

    if action_type == 'button':
        action_value = action['value']
    elif action_type == 'select':
        action_value = action['selected_options'][0]['value']

    original_attachments = original_message['attachments']

    if action_name == 'translate':
        # Translate button.
        attachments = handle_translate_button(review_id, package_name, original_attachments, service)
        response['attachments'] = attachments

    elif action_name == 'reply':
        # Reply button.
        attachments = handle_reply_button(review_id, package_name, original_attachments, service, action_value)
        response['attachments'] = attachments

    else:
        assert(False)

    # Replace the old message.
    response['replace_original'] = True

def handle_message_menu(params, response, service):
    # Input value.
    value = params['value']
    response['options'] = []

    # Echo the value.
    response['options'].append({
        'text' : value,
        'value' : value
    })

    # Pre-defined replies are not useful (can not see all lines).
    return

    # Pre-defined replies.
    # https://docs.google.com/document/d/1pVQTriN4YoybD3T7xegmvjY9vgqar8ivP2BvyHQshg4/edit?ts=5677c503

    # Dùng cho: Phàn nàn về game lỗi hay ko hài lòng về hiệu năng.
    # Usage: Complains about game bugs or Dissatisfaction.
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '\n'
            'Please give us more details of your dissatisfaction, we will fix it for you!'
            '\n'
            'Thanks again, and please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_0'
    })

    # Dùng cho: Phàn nàn về game kém hay hoặc thiếu tính năng.
    # Usage: Complains about bad games or missing features.
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '"\n"'
            'We think it make this game more challenge!'
            '\n'
            'Let\'s wait for next versions for cool gameplay, it will be coming soon!'
            '\n'
            'Thanks again, and please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_1'
    })

    # Dùng cho: Đánh giá vô tội vạ chả biết lý do gì, hoặc chỉ đánh giá tệ.
    # Usage: Complains about what-is-the-reason or just low ratings.
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '\n'
            'We wish you have enjoy this game.'
            '\n'
            'So please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_2'
    })

    # Dùng cho: Có vẻ lỗi gì đó nhưng không nêu rõ.
    # Usage: Complains about unknown bugs.
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '\n'
            'We think it make this game more challenge!'
            '\n'
            'Let\'s wait for the next version for cool gameplay, it will be coming soon!',
            '\n'
            'Thanks again, and please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_3'
    })

    # Dùng cho: Có ý kiến cập nhật hay sửa theo nhu cầu cá nhân (cách chơi, nhiều quảng cáo,...)
    # Usage: Personal opinion (new gameplay, many ads...)
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '\n'
            'We will fix your problem!'
            '\n'
            'Let\'s wait for next versions for cool gameplay, it will be coming soon!'
            '\n'
            'Thanks again, and please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_4'
    })

    # Vietnamese only.
    # Dùng cho: Có ý kiến cập nhật hay sửa theo nhu cầu cá nhân (cách chơi, nhiều quảng cáo,...)
    response['options'].append({
        'text' : (
            'Cám ơn bạn đã feedback cho chúng tôi!'
            '\n'
            'Chúng tôi luôn muốn người dùng đạt trải nghiệm tốt nhất.'
            '\n'
            'Xin hãy cho 5★ đo là động lực để chúng tôi phát triển trò chơi này tốt hơn!'
        ),
        'value' : 'reply_5'
    })

def filter_reviews(reviews, seconds_since_epoch):
    return [review for review in reviews if get_user_last_modifier(review) > seconds_since_epoch]

def fetch_reviews(service, package_name, max_results):
    try:
        reviews = service.reviews().list(
            packageName=package_name,
            maxResults=max_results
        ).execute()
        return reviews

    except Exception as e:
        return None

def help(response):
    response['text'] = (
        '`/reviews help` - Display this text\n'
        '`/reviews [package name]` - Alias for `/reviews auto [package name]`\n'
        '`/reviews auto [package name]` - Display all newest reviews since the last _automatic_ call by bot, upto 20 reviews\n'
        '`/reviews manual [package name]` - Display all reviews since the last _manual_ call by user, upto 20 reviews\n'
        '`/reviews show [number] [package name]` - Display the newest `number` reviews, upto 20 reviews\n'
        '`/reviews package list` - Display registered application packages for automatic call\n'
        '`/reviews package add [package name]` - Add an application package to automatic call\n'
        '`/reviews package remove [package name]` - Remove an application package form automatic call'
    )    
    response['mrkdwn_in'] = ['text']

def show(response):
    pass

def handle_command(params, response, service, config):
    user_id         = params['user_id']
    channel_id      = params['channel_id']
    text            = params['text']
    response_url    = params['response_url']
    team_id         = params['team_id']
    channel_name    = params['channel_name']
    token           = params['token']
    command         = params['command']
    team_domain     = params['team_domain']
    user_name       = params['user_name']

    if command != '/reviews':
        return

    def __auto(package_name):
        pass

    def __manual(package_name):
        pass

    commands = []
    commands.append(Command(signature='help',       callback=lambda:help(response)))
    commands.append(Command(signature='auto %s',    callback=__auto))
    commands.append(Command(signature='manual %s',  callback=__manual))
    commands.append(Command(signature='show %d %s', callback=show))

    params = text.split(' ')
    print 'params = %s' % params

    succeeded = False
    for command in commands:
        if command.execute(params):
            succeeded = True
            break

    # if sub_command == 'manual' or sub_command == 'auto' or sub_command.isdigit():
    #     # Limit to 50 results only or there will be timeout.
    #     max_results = 50
    #     if sub_command.isdigit():
    #         max_results = min(max_results, int(sub_command))

    #     response['response_type'] = 'in_channel'

    #     if succeeded:
    #         attachments = []
    #         reviews = reviews_page['reviews']

    #         print 'review_count = %d' % len(reviews)

    #         # Slow!
    #         # image_url = get_cover_image_url(read_source(get_store_link(package_name)))

    #         for review in reviews:
    #             attachment = format_user_comment(review, package_name)

    #             add_translate_button(attachment)
    #             add_reply_button(attachment)

    #             # Add a footer icon if any.
    #             # if image_url != None:
    #             #    attachment['footer_icon'] = image_url

    #             attachments.append(attachment)

    #             dev_attachment = format_developer_comment(review, package_name)
    #             if dev_attachment != None:
    #                 attachments.append(dev_attachment)

    #         response['attachments'] = attachments

    #         review_count = len(reviews)
    #         response['text'] = 'There are %d reviews for %s' % (review_count, package_name)
    #         config.set_manual_time_point(package_name, get_seconds_since_epoch())

# https://gist.github.com/bradmontgomery/2219997
# https://stackoverflow.com/questions/21631799/how-can-i-pass-parameters-to-a-requesthandler
def MakeHandlerClass(service, config):
    class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler, object):
        def __init__(self, *args, **kwargs):
            self.service = service
            self.config = config
            super(MyHandler, self).__init__(*args, **kwargs)

        def _set_headers(self):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

        def do_GET(self):
            print 'do_GET'
            self._set_headers()

        def do_HEAD(self):
            print 'do_HEAD'
            self._set_headers()

        def do_POST(self):
            print 'do_POST'
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            print 'length = %d' % content_length
            # print 'data = %s' % post_data

            qsl_data = urlparse.parse_qsl(post_data)

            params = dict(qsl_data)
            # print '========================================================================'
            # print 'params = %s' % json.dumps(params, indent=4)

            response = {}

            payload = params.get('payload')
            if payload != None:
                response['response_type'] = 'in_channel'

                # Button.
                print 'Button type'
                payload_dict = json.loads(payload)
                print 'payload = %s' % json.dumps(payload_dict, indent=4)

                original_message = payload_dict.get('original_message')
                if original_message == None:
                    print 'Message menu type'
                    # Message menu.
                    handle_message_menu(payload_dict, response, service)
                    
                else:
                    print 'Message button type'
                    # Message button or an option in message menu was selected.
                    handle_message_button(payload_dict, response, service)
            else:
                print 'Command type'
                print json.dumps(params, indent=4) 
                # Command.
                handle_command(params, response, service, config)

            print 'response = %s' % json.dumps(response, indent=4)

            self._set_headers()
            self.wfile.write(json.dumps(response))
            return

    return MyHandler

# # https://stackoverflow.com/questions/11348025/api-to-get-android-google-play-reviewsgetting-device-name-and-app-version
def connect_google_client():
    credentials = oauth2client.service_account.ServiceAccountCredentials.from_json_keyfile_name(
        JSON_FILE, scopes=['https://www.googleapis.com/auth/androidpublisher'])
    service = apiclient.discovery.build('androidpublisher', 'v2', http=credentials.authorize(httplib2.Http()))
    return service

def run_server(service, config):
    try:
        server = BaseHTTPServer.HTTPServer(('', config.get_http_port()), MakeHandlerClass(service, config))
        print 'Started HTTP server on port %s' % config.get_http_port()

        server.serve_forever()
    except KeyboardInterrupt:
        print '^C received, shutting down the web server'
        pass
    server.server_close()

if __name__ == '__main__':
    service = connect_google_client()
    config = Config()

    for package in PACKAGE_LIST:
        config.add_package(package)

    run_server(service, config)