# Custom date/time formats for en locale
DATE_FORMAT = 'd.m.Y'
DATETIME_FORMAT = 'd.m.Y H:i'
SHORT_DATE_FORMAT = 'd.m.Y'
SHORT_DATETIME_FORMAT = 'd.m.Y H:i'

DATE_INPUT_FORMATS = [
    '%d.%m.%Y',
    '%Y-%m-%d',
]
DATETIME_INPUT_FORMATS = [
    '%d.%m.%Y %H:%M:%S',
    '%d.%m.%Y %H:%M',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
]
