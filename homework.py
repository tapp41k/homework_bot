import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv

from exception import GetStatusException
load_dotenv()

logger = logging.getLogger('my_logger')
logger.setLevel(logging.DEBUG)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def check_tokens():
    """Проверяет доступ к переменным окружения, необходимых для работы бота."""
    return all([TELEGRAM_TOKEN, PRACTICUM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logger.info(f'Сообщение готово к отправке:{message}')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Бот отправил сообщение {message}')
    except telegram.error.TelegramError as error:
        error_message = f'Ошибка при отправке сообщения: {error}'
        logger.error(error_message)


def get_api_answer(timestamp):
    """Выполняет запрос к эндпоинту API-сервиса."""
    params = {'from_date': timestamp}

    try:
        logger.info('Отправлен запрос к API.')
        homework_statuses = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params=params,
        )
    except requests.exceptions.RequestException as error:
        error_message = f'Ошибка при запросе к API: {error}'
        raise ConnectionError(error_message)

    status_code = homework_statuses.status_code
    if status_code != HTTPStatus.OK:
        raise GetStatusException(
            f'"{ENDPOINT}" - недоступен. Код ответа API: {status_code}'
        )

    return homework_statuses.json()


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError('API вернул список неправильного формата')

    if 'homeworks' not in response:
        raise TypeError('API вернул ответ без списка домашних работ')

    if 'current_date' not in response:
        raise TypeError('API вернул ответ без текущей даты домашних работ')

    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('API вернул список неправильного формата')
    return homeworks


def parse_status(homework):
    """Извлекает статус работы из информации о конкретной домашней работе."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ "homework_name" в ответе API')

    if 'status' not in homework:
        raise KeyError('Отсутствует ключ "status" в ответе API')

    if homework_status not in HOMEWORK_VERDICTS.keys():
        raise KeyError('Недокументированный статус домашней работы')

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical('Отсутствует необходимое кол-во'
                         ' переменных окружения')
        sys.exit('Отсутсвуют переменные окружения')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    logger.debug(f'Старт работы бота {timestamp}')
    while True:
        logger.debug(f'Старт новой этерации {timestamp}')
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework:
                message = parse_status(homework[0])
                if message:
                    send_message(bot, message)
                timestamp = response.get('current_date')
            else:
                logger.debug('статус работы не обновился')
        except Exception as error:
            logger.error(f'ошибка: {str(error)}')
            send_message(bot, f'Произошла ошибка: {str(error)}')
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        format=('%(asctime)s'
                '%(levelname)s'
                '%(message)s'
                '%(name)s'),
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler('logfile.log',
                                maxBytes=50000000,
                                backupCount=5)])
    main()
