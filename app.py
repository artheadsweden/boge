from flask import Flask, render_template
import asyncio
from concurrent.futures import ThreadPoolExecutor
import requests
import feedparser
from time import strftime
import datetime
from dateutil import rrule
import locale
import json

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return json.JSONEncoder.default(self, obj)

app = Flask(__name__)


def get_current_and_next_program(channel_id):
    schedule_url = f'https://api.sr.se/v2/scheduledepisodes/rightnow?format=json&channelid={channel_id}'
    schedule = requests.get(schedule_url).json()
    current_program = {
        'title': schedule['channel']['currentscheduledepisode']['title'],
        'imageurl': schedule['channel']['currentscheduledepisode']['socialimage'],
        'starttime': datetime.datetime.fromtimestamp(int(schedule['channel']['currentscheduledepisode']['starttimeutc'][6:-2]) / 1000),
        'endtime': datetime.datetime.fromtimestamp(int(schedule['channel']['currentscheduledepisode']['endtimeutc'][6:-2]) / 1000)
    }
    next_program = {
        'title': schedule['channel']['nextscheduledepisode']['title'],
        'imageurl': schedule['channel']['nextscheduledepisode']['socialimage'],
        'starttime': datetime.datetime.fromtimestamp(int(schedule['channel']['nextscheduledepisode']['starttimeutc'][6:-2]) / 1000),
        'endtime': datetime.datetime.fromtimestamp(int(schedule['channel']['nextscheduledepisode']['endtimeutc'][6:-2]) / 1000)
    }
 
    return current_program, next_program

def get_sr():
    channels_url = 'http://api.sr.se/api/v2/channels?format=json'
    channels = requests.get(channels_url).json()
    channel_names = ['P1', 'P2', 'P3', 'P4 Gotland']
    channels = {channel['name']: channel for channel in channels['channels'] if channel['name'] in channel_names}
    channel_list = []
    for channel in channels:
        current_program, next_program = get_current_and_next_program(channels[channel]['id'])
        c = {
            'name': channel,
            'url': channels[channel]['liveaudio']['url'],
            'current_program': current_program['title'] if len(current_program['title']) < 20 else current_program['title'][:20] + '...',
            'current_program_image': current_program['imageurl'],
            'current_program_starttime': current_program['starttime'],
            'current_program_endtime': current_program['endtime'],
            'next_program': next_program['title'] if len(next_program['title']) < 20 else next_program['title'][:20] + '...',
            'next_program_image': next_program['imageurl'],
            'next_program_starttime': next_program['starttime'],
            'next_program_endtime': next_program['endtime'],
            'channel_img': channels[channel]['image'],
            'channel_id': channels[channel]['id']
        }
        channel_list.append(c)
    return channel_list

def get_mail(zip):
    url = f'https://portal.postnord.com/api/sendoutarrival/closest?postalCode={zip}'
    mail = requests.get(url).json()
    return mail

def get_trash(start_date, interval):
    # Get the date of the next trash collection from today
    today = datetime.datetime.today()
    if today < start_date:
        next_collection = start_date
    else:
        next_collection = rrule.rrule(rrule.WEEKLY, interval=interval, dtstart=start_date).after(today)

    return next_collection.date()

def get_water_temp():
    response = requests.post("https://gotlandsenergi.se/badapp//Home/buoyGraf", headers={'User-Agent': 'Mozilla/5.0'})
    #open('test.html', 'w').write(response.text)
    water = 'N/A'
    air = 'N/A'
    for i, line in enumerate(response.text.splitlines()):
        if "<td>Åminne</td>" in line.strip():
            water = response.text.splitlines()[i+1].strip()[4:-6]
            air = response.text.splitlines()[i+2].strip()[4:-6]
            break
    return water, air

def get_weather(lat, lng):
    url = f'https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2/geotype/point/lon/' + str(lng) + '/lat/' + str(lat) + '/data.json'
    weather = requests.get(url).json()
    now_temp = [i for i in weather['timeSeries'][0]['parameters'] if i['name'] == 't'][0]['values'][0]
    tomorrow_temp = [i for i in weather['timeSeries'][24]['parameters'] if i['name'] == 't'][0]['values'][0]
    current_weather = {
        'temperature':now_temp,
        'icon': weather['timeSeries'][0]['parameters'][18]['values'][0]
    }
    tomorrow_weather = {
        'temperature': tomorrow_temp,
        'icon': weather['timeSeries'][24]['parameters'][18]['values'][0]
    }
    return current_weather, tomorrow_weather

def get_latest_feeds(num_entries=3):
    feed_url = "https://helagotland.se/rss/lokalt"
    response = requests.get(feed_url)
    response.encoding = 'utf-8'  # force utf-8 encoding
    feed_content = response.text

    feed = feedparser.parse(feed_content)
    
    # Swedish month names
    months_swedish = {
        1: 'januari', 2: 'februari', 3: 'mars', 4: 'april', 5: 'maj',
        6: 'juni', 7: 'juli', 8: 'augusti', 9: 'september',
        10: 'oktober', 11: 'november', 12: 'december'
    }

    entries = []
    for entry in feed.entries:
        pub_time = entry.published_parsed
        pub_str = strftime('%H:%M:%S, %d ', pub_time) + months_swedish[pub_time.tm_mon] + strftime(', %Y', pub_time)
        entries.append({'title': entry.title, 'time': pub_str})

    return entries[:num_entries]

def fetch_data():
    return get_sr(), get_mail('62436'), get_trash(datetime.datetime(2023, 5, 25), 2), get_weather(57.67882, 18.76912), get_water_temp(), get_latest_feeds(5)

def update():
    locale.setlocale(locale.LC_TIME, "sv_SE.utf8")
    radio, mail, trash, weather, temp, news = fetch_data()
    data = {
    'today_weather': {
        'temperature': weather[0]['temperature'],
        'image': str(weather[0]['icon'])+'.png'
    },
    'tomorrow_weather': {
        'temperature': weather[1]['temperature'],
        'image': str(weather[1]['icon'])+'.png'
    },
    'mail_delivery': {
        'next': mail['delivery'],
        'upcoming': mail['upcoming'],
        'image': 'mail-box.png'
    },
    'trash_collection': {
        'date': trash.strftime('%d %B, %Y'),
        'image': 'trashcan.png'
    },
    'water_temp': {
        'temperature': temp[0],
        'air_temp': temp[1],
        'image': 'water.png'
    },
    'radio_channels': radio,
    'volume': 50,
    'power': 'ON',
    'news': news,
    }
    return data

@app.route('/')
def index():
    data = update()
    return render_template('radio.html', data=data)

@app.route('/update')
def update_data():
    data = update()
    return json.dumps(data, cls=CustomJSONEncoder)

app.run(debug=True)