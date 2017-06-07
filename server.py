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
DEFAULT_REFRESH_INTERVAL = 86400 # Seconds.
JSON_FILE = 'GooglePlayCustomerService-ae3d674c4880.json' # Use your JSON.
WEBHOOK_URL = 'https://hooks.slack.com/services/T05______/B5N______/u7i_____________________' # Use your webhook url.
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
            return True
        return False

    @classmethod
    def __remove_unique(cls, lst, val):
        if val not in lst:
            return False
        lst.remove(val)
        return True

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

    def get_refresh_interval(self):
        return self.__get_settings_object().get('refresh_interval', DEFAULT_REFRESH_INTERVAL)

    def set_refresh_interval(self, seconds):
        self.__get_settings_object()['refresh_interval'] = seconds
        self.write_config_data()

    def __lazy_init_refresh_time_point(self):
        settings = self.__get_settings_object()
        if not 'last_refresh' in settings:
            settings['last_refresh'] = get_seconds_since_epoch()
            self.write_config_data()

    def get_last_refresh_time_point(self):
        self.__lazy_init_refresh_time_point()
        return self.__get_settings_object()['last_refresh']

    def set_last_refresh_time_point(self, seconds_since_epoch):
        self.__get_settings_object()['last_refresh'] = seconds_since_epoch
        self.write_config_data()

    def get_package_list(self):
        settings = self.__get_settings_object()
        return Config.__get_array(settings, 'packages')

    def add_package(self, package_name):
        inserted = Config.__append_unique(self.get_package_list(), package_name)
        if inserted:
            self.write_config_data()
        return inserted

    def remove_package(self, package_name):
        erased = Config.__remove_unique(self.get_package_list(), package_name)
        if erased:
            self.write_config_data()
        return erased

class Command:
    __params = None
    __callback = None

    def __init__(self, signature, callback):
        self.__params = signature.split(' ')
        self.__callback = callback

    def execute(self, params):
        if len(self.__params) != len(params):
            # print 'command = %s found %s' % (self.__params, params)
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

            if __param == '%s':
                # Expect a string.
                placeholders.append(param)
                i = i + 1
                continue

            if __param == '%d':
                # Expect an integer.
                if not param.isdigit():
                    # print 'command = %s expected an integer found %s' % (self.__params, param)
                    return False

                placeholders.append(param)
                i = i + 1
                continue

            # print 'command = %s expected %s found %s' % (self.__params, __param, param)
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

    def __get_user_last_modified_string(self):
        return self.__get_user_comment_object()['lastModified']['seconds']

    def get_user_last_modified(self):
        return int(self.__get_user_last_modified_string())

    def get_star_rating(self):
        return self.__get_user_comment_object()['starRating']

    def get_star_repr(self):
        return parse_stars(self.get_star_rating())

    def get_color(self):
        return color_for_stars(self.get_star_rating())

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
        if self.get_author_name() != None and len(self.get_author_name()) > 0:
            author_texts.append(self.get_author_name())

        # User's country.
        author_texts.append(self.get_user_country())

        attachment['author_name'] = u' · '.join(author_texts)

        # Footer.
        footer_texts = []

        # Package name.
        footer_texts.append(package_name)

        # Store link.
        footer_texts.append('<%s|Store Link>' % get_store_link(package_name))

        # Use Google Translation.
        google_translation_link = get_google_translation_link('auto', 'en', self.get_user_comment().encode('utf8'))
        if len(google_translation_link) < 120:
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
    return time.strftime("%b %-d, %Y at %-I:%M:%S %p", time.gmtime(int(seconds_since_epoch)))

# https://stackoverflow.com/questions/4548684/how-to-get-the-seconds-since-epoch-from-the-time-date-output-of-gmtime-in-py
def get_seconds_since_epoch():
    return int(time.time())

# https://stackoverflow.com/questions/3168096/getting-computers-utc-offset-in-python
def get_timezone_offset():
    return -time.timezone

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

    # Keep `text` field.
    response['text'] = original_message.get('text', '')

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
    return [review for review in reviews if Review(review).get_user_last_modified() > seconds_since_epoch]

def fetch_reviews(service, package_name, max_results):
    try:
        reviews = service.reviews().list(
            packageName=package_name,
            maxResults=max_results
        ).execute()
        return reviews['reviews']

    except Exception as e:
        return None

def create_attachments(reviews, package_name):
    attachments = []

    # Slow!
    # image_url = get_cover_image_url(read_source(get_store_link(package_name)))

    for __review in reviews:
        review = Review(__review)
        attachment = review.format_user_comment(package_name)

        add_translate_button(attachment)
        add_reply_button(attachment)

        # Add a footer icon if any.
        # if image_url != None:
        #    attachment['footer_icon'] = image_url

        attachments.append(attachment)

        if review.has_developer_comment():
            attachments.append(review.format_developer_comment(package_name))

    return attachments


def show_help(response):
    response['text'] = (
        '`/reviews help` - Display this text\n'
        '`/reviews [package name]` - Alias for `/reviews auto [package name]`\n'
        '`/reviews auto [package name]` - Display all newest reviews since the last _automatic_ call by bot, upto 20 reviews\n'
        '`/reviews manual [package name]` - Display all reviews since the last _manual_ call by user, upto 20 reviews\n'
        '`/reviews show [number] [package name]` - Display the newest `number` reviews, upto 20 reviews\n'
        '`/reviews package list` - Display registered application packages for automatic call\n'
        '`/reviews package add [package name]` - Add an application package to automatic call\n'
        '`/reviews package remove [package name]` - Remove an application package form automatic call\n'
        '`/reviews refresh interval [seconds]` - Set the refresh interval in seconds, should be larger than 60 seconds\n'
        '`/reviews refresh schedule [seconds since now]` - Reset the next refresh to be the specified time point\n'
        '`/reviews refresh info` - Print the refresh interval and next scheduled refresh time'
    )    
    response['mrkdwn_in'] = ['text']

def attach_reviews_to_response(response, reviews, package_name):
    attachments = create_attachments(reviews, package_name)
    response['attachments'] = attachments
    review_count = len(reviews)

    if review_count == 0:
        response['text'] = 'There is not any review for %s' % package_name
    elif review_count == 1:
        response['text'] = 'There is a review for %s' % package_name
    else:
        response['text'] = 'There are %d reviews for %s' % (review_count, package_name)

def show_reviews(response, service, config, package_name, max_results, seconds_since_epoch):
    print max_results
    reviews = fetch_reviews(service, package_name, max_results)
    if reviews == None:
        return 0

    print json.dumps(reviews, indent=2)

    reviews = filter_reviews(reviews, seconds_since_epoch)
    attach_reviews_to_response(response, reviews, package_name)

    response['response_type'] = 'in_channel'
    return len(reviews)

def show_reviews_with_auto_mode(response, service, config, package_name, max_result, seconds_since_epoch):
    config.set_auto_time_point(package_name, get_seconds_since_epoch())
    return show_reviews(response, service, config, package_name, max_result, seconds_since_epoch)

def show_reviews_with_manual_mode(response, service, config, package_name, max_result, seconds_since_epoch):
    config.set_manual_time_point(package_name, get_seconds_since_epoch())
    return show_reviews(response, service, config, package_name, max_result, seconds_since_epoch)

def show_packages(response, config):
    packages = config.get_package_list()
    response['response_type'] = 'in_channel'
    if len(packages) == 0:
        response['text'] = 'There is not any registered package'
    else:
        response['text'] = '\n'.join(sorted(packages))

def add_package(response, config, package_name):
    inserted = config.add_package(package_name)
    response['response_type'] = 'in_channel'
    if inserted:
        response['text'] = 'Package added successfully!'
    else:
        response['text'] = 'Package already added!'

def remove_package(response, config, package_name):
    erased = config.remove_package(package_name)
    response['response_type'] = 'in_channel'
    if erased:
        response['text'] = 'Package removed successfully!'
    else:
        response['text'] = 'Package doesn\'t exist!'

def set_refresh_interval(response, config, seconds):
    config.set_refresh_interval(seconds)
    next_refresh_time_point = config.get_last_refresh_time_point() + seconds
    response['response_type'] = 'in_channel'

    lines = []
    lines.append('Refresh interval changed to %d seconds' % seconds)
    lines.append('Next refresh: %s' % parse_time_point(next_refresh_time_point + get_timezone_offset()))
    response['text'] = '\n'.join(lines)

def schedule_next_refresh(response, config, seconds_since_now):
    seconds_since_epoch = get_seconds_since_epoch() + seconds_since_now
    config.set_last_refresh_time_point(seconds_since_epoch - config.get_refresh_interval())
    response['response_type'] = 'in_channel'
    response['text'] = 'Next refresh: %s' % parse_time_point(seconds_since_epoch + get_timezone_offset())

def print_next_refresh(response, config):
    response['response_type'] = 'in_channel'
    last_refresh = config.get_last_refresh_time_point()
    refresh_interval = config.get_refresh_interval()

    lines = []
    lines.append('Current refresh interval: %d (seconds)' % refresh_interval)
    lines.append('Next refresh:')
    lines.append('%s' % parse_time_point(last_refresh + refresh_interval * 1 + get_timezone_offset()))
    lines.append('%s' % parse_time_point(last_refresh + refresh_interval * 2 + get_timezone_offset()))
    lines.append('%s' % parse_time_point(last_refresh + refresh_interval * 3 + get_timezone_offset()))
    response['text'] = '\n'.join(lines)

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
    commands.append(Command(
        signature='help',
        callback=lambda:
            show_help(response)
    ))
    commands.append(Command(
        signature='auto %s',
        callback=lambda package_name:
            show_reviews_with_auto_mode(response, service, config, package_name, 20, config.get_auto_time_point(package_name))
    ))
    commands.append(Command(
        signature='manual %s',
        callback=lambda package_name:
            show_reviews_with_manual_mode(response, service, config, package_name, 20, config.get_manual_time_point(package_name))
    ))
    commands.append(Command(
        signature='show %d %s',
        callback=lambda max_result, package_name:
            show_reviews(response, service, config, package_name, min(int(max_result), 20), 0),
    ))
    commands.append(Command(
        signature='package list',
        callback=lambda:
            show_packages(response, config)
    ))
    commands.append(Command(
        signature='package add %s',
        callback=lambda package_name:
            add_package(response, config, package_name)
    ))
    commands.append(Command(
        signature='package remove %s',
        callback=lambda package_name:
            remove_package(response, config, package_name)
    ))
    commands.append(Command(
        signature='refresh interval %d',
        callback=lambda seconds:
            set_refresh_interval(response, config, max(int(seconds), 60))
    ))
    commands.append(Command(
        signature='refresh schedule %d',
        callback=lambda seconds_since_now:
            schedule_next_refresh(response, config, int(seconds_since_now))
    ))
    commands.append(Command(
        signature='refresh info',
        callback=lambda:
            print_next_refresh(response, config)
    ))

    params = text.split(' ')
    print 'params = %s' % params

    succeeded = False
    for command in commands:
        if command.execute(params):
            succeeded = True
            break

    if not succeeded:
        response['text'] = 'Invalid command'

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

# https://stackoverflow.com/questions/2223157/how-to-execute-a-function-asynchronously-every-60-seconds-in-python
def schedule_automatic_refresh(service, config):
    def __every_second():
        current_time = get_seconds_since_epoch()
        last_refresh = config.get_last_refresh_time_point()
        next_refresh = last_refresh + config.get_refresh_interval()

        if current_time >= next_refresh:
            packages = config.get_package_list()
            for package_name in packages:
                payload = {}
                review_count = show_reviews_with_auto_mode(payload, service, config, package_name, 20, last_refresh)

                if review_count > 0:
                    # https://stackoverflow.com/questions/9746303/how-do-i-send-a-post-request-as-a-json
                    response = requests.post(
                        WEBHOOK_URL,
                        data=json.dumps(payload),
                        headers={'content-type': 'application/json'}
                    )

            config.set_last_refresh_time_point(current_time)

        threading.Timer(3, __every_second).start()

    __every_second()

if __name__ == '__main__':
    service = connect_google_client()
    config = Config()

    for package in PACKAGE_LIST:
        config.add_package(package)

    schedule_automatic_refresh(service, config)
    run_server(service, config)