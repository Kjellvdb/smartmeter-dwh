from datetime import datetime
from logging.handlers import RotatingFileHandler
from flasgger import Swagger
from flask import Flask, jsonify, request
from sqlalchemy import text

import logging
import os
import shutil

from smartmeter import config
from smartmeter.db import get_engine

MAX_LOGFILE_SIZE_MB = config.MAX_LOGFILE_SIZE_MB
connection = get_engine()

# ----- Logging Configuration -----
log_dir = str(config.LOG_DIR)
log_file = str(config.LOG_DIR / 'smartmeter-api.log')
if not os.path.exists(os.path.dirname(log_file)):
    os.makedirs(os.path.dirname(log_file))

log_handler = RotatingFileHandler(log_file, maxBytes=int(MAX_LOGFILE_SIZE_MB) * 1024 * 1024, backupCount=10)
log_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
def rollover_function():
    timestamp = datetime.now().strftime('%Y-%m-%d')
    backup_file = os.path.join(log_dir, f'digitale-meter-{timestamp}.log')

    shutil.copy(log_file, backup_file)
    open(log_file, 'w').close()
log_handler.doRollover = rollover_function

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

def log(route, method, status_code, api_key=None, params=None, response=None):
    path = f'{method} {route}'
    if params:
        params = '&'.join([f'{key}={value}' for key, value in params.items()])
        path = f'{path}?{params}'
    log_message = f'{path} - {status_code} - {response}'
    if api_key:
        log_message += f' - API Key: {api_key[:4]}***'

    if str(status_code).startswith('2'):
        logger.info(log_message)
    elif str(status_code).startswith('3') or str(status_code).startswith('4'):
        logger.warning(log_message)
    elif str(status_code).startswith('5'):
        logger.error(log_message)
    else:
        logger.debug(log_message)

logging.getLogger('werkzeug').disabled = True

# ----- Flask API -----
app = Flask(__name__)
swagger = Swagger(app)

@app.route('/UsageAndInjectionPerMonth/<EANID>', methods=['GET'])
def getTotalUsageAndInjection(EANID):
    """
    Retrieve the total usage and injection for a specific user and month.
    ---
    parameters:
      - name: EANID
        in: path
        required: true
        type: string
        description: The EANID of the user.
      - name: YYYYMM
        in: query
        required: true
        type: string
        description: The month in the format YYYYMM.
    responses:
      200:
        description: The total usage and injection for the specified month and user.
        schema:
          type: object
          properties:
            TotalInjection:
              type: number
              example: 517.337000
            TotalUsage:
              type: number
              example: 353.441000
      400:
        description: 
          - Parameter 'YYYYMM' is required.
          - Parameter 'EANID' has to be a valid number.
      404:
        description: No data found.
    """
    if not EANID.isdigit():
        response = 'Parameter \'EANID\' has to be a valid number.'
        status_code = 400
        log(request.path, request.method, status_code, request.headers.get('X-API-KEY'), request.args, response)
        return jsonify({'error': response}), status_code

    YYYYMM = request.args.get('YYYYMM')
    if not YYYYMM:
        response = 'Parameter \'YYYYMM\' is required.'
        status_code = 400
        log(request.path, request.method, status_code, request.headers.get('X-API-KEY'), request.args, response)
        return jsonify({'error': response}), status_code

    with connection.connect() as conn:
        result = conn.execute(text('EXEC getTotalUsageAndInjection @EANID = :EANID, @YYYYMM = :YYYYMM'), parameters={
            'EANID': int(EANID),
            'YYYYMM': str(YYYYMM)
        })
        row = result.fetchone()

    if not row or row.TotalInjection is None:
        response = 'No data found.'
        status_code = 404
        log(request.path, request.method, status_code, request.headers.get('X-API-KEY'), request.args, response)
        return jsonify({'message': response}), status_code

    response = row._asdict()
    status_code = 200
    log(request.path, request.method, status_code, request.headers.get('X-API-KEY'), request.args, response)
    return jsonify(response), status_code

@app.route('/AverageHoursSunPerDay/<WeatherStationID>', methods=['GET'])
def getAverageHoursSunPerDay(WeatherStationID):
    """
    Retrieve the average hours of sun per day for a specific weather station over the last month.
    ---
    parameters:
      - name: WeatherStationID
        in: path
        required: true
        type: string
        description: The ID of the weather station.
    responses:
      200:
        description: Average hours of sun per day for the specified weather station.
        schema:
          type: object
          properties:
            AverageHoursSunPerDay:
              type: number
              example: 8.5333333333
      400:
        description: Parameter 'WeatherStationID' has to be a valid number.
      404:
        description: No data found.
    """
    if not WeatherStationID.isdigit():
        response = 'Parameter \'WeatherStationID\' has to be a valid number.'
        status_code = 400
        log(request.path, request.method, status_code, request.headers.get('X-API-KEY'), request.args, response)
        return jsonify({'error': response}), status_code

    with connection.connect() as conn:
        result = conn.execute(text('EXEC getAverageHoursSunPerDay @WeatherStationID = :WeatherStationID'), parameters={
            'WeatherStationID': int(WeatherStationID)
        })
        row = result.fetchone()

    if not row or row.AverageHoursSunPerDay is None:
        response = 'No data found.'
        status_code = 404
        log(request.path, request.method, status_code, request.headers.get('X-API-KEY'), request.args, response)
        return jsonify({'message': response}), status_code

    response = row._asdict()
    status_code = 200
    log(request.path, request.method, status_code, request.headers.get('X-API-KEY'), request.args, response)
    return jsonify(response), status_code

@app.route('/UpdateBelpexPrice', methods=['PUT'])
def addBelpexPrice():
    """
    Update the Belpex price.
    ---
    parameters:
      - name: BelpexValue
        in: query
        required: true
        type: number
        description: The value of the Belpex price.
      - name: BelpexType
        in: query
        required: true
        type: string
        description: The type of the Belpex price.
      - name: DateKey
        in: query
        required: true
        type: string
        description: The date in the format YYYYMMDD.
      - name: FullTime
        in: query
        required: true
        type: string
        description: The time in the format HH:MM:SS.
    responses:
      200:
        description: BelpexValue updated successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              example: BelpexValue updated successfully.
      400:
        description: Parameters 'BelpexValue', 'BelpexType', 'DateKey' and 'FullTime' are required.
      401:
        description: Invalid or missing API key.
    """
    api_key = request.headers.get('X-API-KEY')
    if not api_key or not validate_api_key(api_key):
        response = 'Invalid or missing API key.'
        status_code = 401
        log(request.path, request.method, status_code, api_key, request.args, response)
        return jsonify({'error': response}), status_code

    BelpexValue = request.args.get('BelpexValue')
    BelpexType = request.args.get('BelpexType')
    DateKey = request.args.get('DateKey')
    FullTime = request.args.get('FullTime')
    if not BelpexValue or not BelpexType or not DateKey or not FullTime:
        response = 'Parameters \'BelpexValue\', \'BelpexType\', \'DateKey\' and \'FullTime\' are required.'
        status_code = 400
        log(request.path, request.method, status_code, api_key, request.args, response)
        return jsonify({'error': response}), status_code

    with connection.begin() as conn:
        conn.execute(text('EXEC updateBelpexValue  @BelpexValue = :BelpexValue, @BelpexType = :BelpexType, @DateKey = :DateKey, @FullTime = :FullTime'), parameters={
            'BelpexValue': float(BelpexValue),
            'BelpexType': str(BelpexType),
            'DateKey': int(DateKey),
            'FullTime': str(FullTime)
        })

    response = 'BelpexValue updated successfully.'
    status_code = 200
    log(request.path, request.method, status_code, api_key, request.args, response)
    return jsonify({'message': response}), status_code

def validate_api_key(api_key):
    return bool(api_key) and api_key == os.getenv('API_KEY')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
