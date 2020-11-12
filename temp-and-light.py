#!/usr/bin/env python3
# -*- coding: utf-8 -*-

f"Sorry! This program requires Python >= 3.6 😅"

import os
import time
import numpy
import colorsys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fonts.ttf import RobotoMedium as UserFont

import ST7735
from bme280 import BME280
from ltr559 import LTR559

import pytz
from pytz import timezone
from astral.geocoder import database, lookup
from astral.sun import sun
from datetime import datetime, timedelta

try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus


def calculate_y_pos(x, centre):
    """Calculates the y-coordinate on a parabolic curve, given x."""
    centre = 80
    y = 1 / centre * (x - centre) ** 2

    return int(y)


def circle_coordinates(x, y, radius):
    """Calculates the bounds of a circle, given centre and radius."""

    x1 = x - radius  # Left
    x2 = x + radius  # Right
    y1 = y - radius  # Bottom
    y2 = y + radius  # Top

    return (x1, y1, x2, y2)


def map_colour(x, centre, start_hue, end_hue, day):
    """Given an x coordinate and a centre point, a start and end hue (in degrees),
       and a Boolean for day or night (day is True, night False), calculate a colour
       hue representing the 'colour' of that time of day."""

    start_hue = start_hue / 360  # Rescale to between 0 and 1
    end_hue = end_hue / 360

    sat = 1.0

    # Dim the brightness as you move from the centre to the edges
    val = 1 - (abs(centre - x) / (2 * centre))

    # Ramp up towards centre, then back down
    if x > centre:
        x = (2 * centre) - x

    # Calculate the hue
    hue = start_hue + ((x / centre) * (end_hue - start_hue))

    # At night, move towards purple/blue hues and reverse dimming
    if not day:
        hue = 1 - hue
        val = 1 - val

    r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, sat, val)]

    return (r, g, b)


def x_from_sun_moon_time(progress, period, x_range):
    """Recalculate/rescale an amount of progress through a time period."""

    x = int((progress / period) * x_range)

    return x


def sun_moon_time(city_name, time_zone):
    """Calculate the progress through the current sun/moon period (i.e day or
       night) from the last sunrise or sunset, given a datetime object 't'."""

    city = lookup(city_name, database())

    # Datetime objects for yesterday, today, tomorrow
    utc = pytz.utc
    utc_dt = datetime.now(tz=utc)
    local_dt = utc_dt.astimezone(pytz.timezone(time_zone))
    today = local_dt.date()
    yesterday = today - timedelta(1)
    tomorrow = today + timedelta(1)

    # Sun objects for yesterday, today, tomorrow
    sun_yesterday = sun(city.observer, date=yesterday)
    sun_today = sun(city.observer, date=today)
    sun_tomorrow = sun(city.observer, date=tomorrow)

    # Work out sunset yesterday, sunrise/sunset today, and sunrise tomorrow
    sunset_yesterday = sun_yesterday["sunset"]
    sunrise_today = sun_today["sunrise"]
    sunset_today = sun_today["sunset"]
    sunrise_tomorrow = sun_tomorrow["sunrise"]

    # Work out lengths of day or night period and progress through period
    if sunrise_today < local_dt < sunset_today:
        day = True
        period = sunset_today - sunrise_today
        # mid = sunrise_today + (period / 2)
        progress = local_dt - sunrise_today

    elif local_dt > sunset_today:
        day = False
        period = sunrise_tomorrow - sunset_today
        # mid = sunset_today + (period / 2)
        progress = local_dt - sunset_today

    else:
        day = False
        period = sunrise_today - sunset_yesterday
        # mid = sunset_yesterday + (period / 2)
        progress = local_dt - sunset_yesterday

    # Convert time deltas to seconds
    progress = progress.total_seconds()
    period = period.total_seconds()

    return (progress, period, day, local_dt)


def draw_background(progress, period, day):
    """Given an amount of progress through the day or night, draw the
       background colour and overlay a blurred sun/moon."""

    # x-coordinate for sun/moon
    x = x_from_sun_moon_time(progress, period, WIDTH)

    # If it's day, then move right to left
    if day:
        x = WIDTH - x

    # Calculate position on sun/moon's curve
    centre = WIDTH / 2
    y = calculate_y_pos(x, centre)

    # Background colour
    background = map_colour(x, 80, mid_hue, day_hue, day)

    # New image for background colour
    img = Image.new('RGBA', (WIDTH, HEIGHT), color=background)
    # draw = ImageDraw.Draw(img)

    # New image for sun/moon overlay
    overlay = Image.new('RGBA', (WIDTH, HEIGHT), color=(0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Draw the sun/moon
    circle = circle_coordinates(x, y, sun_radius)
    overlay_draw.ellipse(circle, fill=(200, 200, 50, opacity))

    # Overlay the sun/moon on the background as an alpha matte
    composite = Image.alpha_composite(img, overlay).filter(ImageFilter.GaussianBlur(radius=blur))

    return composite


def overlay_text(img, position, text, font, align_right=False, rectangle=False):
    draw = ImageDraw.Draw(img)
    w, h = font.getsize(text)
    if align_right:
        x, y = position
        x -= w
        position = (x, y)
    if rectangle:
        x += 1
        y += 1
        position = (x, y)
        border = 1
        rect = (x - border, y, x + w, y + h + border)
        rect_img = Image.new('RGBA', (WIDTH, HEIGHT), color=(0, 0, 0, 0))
        rect_draw = ImageDraw.Draw(rect_img)
        rect_draw.rectangle(rect, (255, 255, 255))
        rect_draw.text(position, text, font=font, fill=(0, 0, 0, 0))
        img = Image.alpha_composite(img, rect_img)
    else:
        draw.text(position, text, font=font, fill=(255, 255, 255))
    return img


def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = f.read()
        temp = int(temp) / 1000.0
    return temp

# Initialise the LCD
disp = ST7735.ST7735(
    port=0,
    cs=1,
    dc=9,
    backlight=12,
    rotation=270,
    spi_speed_hz=10000000
)

disp.begin()

WIDTH = disp.width
HEIGHT = disp.height

# The city and timezone that you want to display.
city_name = "Sheffield"
time_zone = "Europe/London"

# Values that alter the look of the background
blur = 50
opacity = 125

mid_hue = 0
day_hue = 25

sun_radius = 50

# Fonts
font_sm = ImageFont.truetype(UserFont, 12)
font_lg = ImageFont.truetype(UserFont, 14)
font_xl = ImageFont.truetype(UserFont, 28)

# Margins
margin = 3


# Set up BME280 weather sensor
bus = SMBus(1)
bme280 = BME280(i2c_dev=bus)

min_temp = None
max_temp = None

factor = 2.25
cpu_temps = [get_cpu_temperature()] * 5

disp_imperial = True

# Set up light sensor
ltr559 = LTR559()

# Keep track of time elapsed
start_time = time.time()

while True:
    path = os.path.dirname(os.path.realpath(__file__))
    progress, period, day, local_dt = sun_moon_time(city_name, time_zone)
    background = draw_background(progress, period, day)

    # Time.
    time_elapsed = time.time() - start_time
    date_string = local_dt.strftime("%d %b %y").lstrip('0')
    time_string = local_dt.strftime("%H:%M")
    img = overlay_text(background, (0 + margin, 0 + margin), time_string, font_lg)
    img = overlay_text(img, (WIDTH - margin, 0 + margin), date_string, font_lg, align_right=True)

    # Temperature
    temperature = bme280.get_temperature()

    # Corrected temperature
    cpu_temp = get_cpu_temperature()
    cpu_temps = cpu_temps[1:] + [cpu_temp]
    avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
    corr_temperature = temperature - ((avg_cpu_temp - temperature) / factor)

    if time_elapsed > 30:
        if min_temp is not None and max_temp is not None:
            if corr_temperature < min_temp:
                min_temp = corr_temperature
            elif corr_temperature > max_temp:
                max_temp = corr_temperature
        else:
            min_temp = corr_temperature
            max_temp = corr_temperature

    if disp_imperial == True:
        temp_imperial = (corr_temperature * 1.8) + 32
        temp_string = f"{temp_imperial:.0f}°F"
        range_string = "------"
    else:
        temp_string = f"{corr_temperature:.0f}°C"
        if min_temp is not None and max_temp is not None:
            range_string = f"{min_temp:.0f}-{max_temp:.0f}"
        else:
            range_string = "------"
    img = overlay_text(img, (68, 18), temp_string, font_xl, align_right=True)
    spacing = font_xl.getsize(temp_string)[1] + 1
    temp_icon = Image.open(f"{path}/icons/temperature.png")
    img.paste(temp_icon, (margin, 18), mask=temp_icon)

    # Display image
    disp.display(img)