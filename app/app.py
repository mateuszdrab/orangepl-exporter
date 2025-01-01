from flask import Flask, jsonify, request
from prometheus_client import Counter, Gauge, generate_latest, make_wsgi_app
from prometheus_flask_exporter import PrometheusMetrics
import json
import requests
import datetime
import uuid

app = Flask(__name__)
metrics = PrometheusMetrics(app, path=None)
metrics_wsgi_app = make_wsgi_app()

metric_accounts = Gauge('orangepl_accounts_info', 'Orange PL accounts info', [
                        'username', 'customer_id'])
metric_billing_accounts = Gauge(
    'orangepl_billing_accounts_info', 'Orange PL billing accounts info', ['username', 'customer_id', 'billing_account_type', 'billing_account_code', 'billing_account_name'])
metric_prepaid_expiry_date = Gauge('orangepl_prepaid_expiry_date',
                                   'Orange PL prepaid expiry date', ['username', 'customer_id', 'billing_account_code'])
metric_prepaid_cash = Gauge('orangepl_prepaid_cash_pln',
                            'Orange PL prepaid cash', ['username', 'customer_id', 'billing_account_code', 'cash_type'])
metric_prepaid_allowance_data = Gauge('orangepl_prepaid_allowance_data_bytes',
                                      'Orange PL prepaid data allowance', ['username', 'customer_id', 'billing_account_code', 'data_type'])
metric_prepaid_allowance_data_item = Gauge('orangepl_prepaid_allowance_data_item_bytes',
                                           'Orange PL prepaid data allowance breakdown', ['username', 'customer_id', 'billing_account_code', 'data_type', 'description'])
metric_prepaid_allowance_data_item_expiry_date = Gauge('orangepl_prepaid_allowance_data_item_expiry_date',
                                                       'Orange PL prepaid data allowance breakdown expiry date', ['username', 'customer_id', 'billing_account_code', 'data_type', 'description'])

# Orange PL API key obtained from packet capture
x_api_key = 'AkWwc1UIBmg049NurALAr7kUdKfgrsqF'


def get_full_url(url, params):
    query_string = '&'.join([f"{key}={value}" for key, value in params.items()])
    return f"{url}?{query_string}"

@app.get('/metrics')
@metrics.do_not_track()
def get_metrics():
    # Reset metrics gauges
    metric_accounts.clear()
    metric_billing_accounts.clear()
    metric_prepaid_expiry_date.clear()
    metric_prepaid_cash.clear()
    metric_prepaid_allowance_data.clear()
    metric_prepaid_allowance_data_item.clear()
    metric_prepaid_allowance_data_item_expiry_date.clear()

    # read file accounts.json into accounts variable
    with open('accounts.json') as json_file:
        accounts = json.load(json_file)

    # for each account in accounts
    for account in accounts:
        try:            
            state = str(uuid.uuid4())
            nonce = str(uuid.uuid4())

            body = { "DEVICE_NAME": account["deviceName"]}

            headers = {
                'X-Api-Key':            x_api_key,
                'X-OPL-Platform':       'iOS',
                'X-OPL-RequestSource':  'mobiapp',
                'X-OPL-Device': account['device']
            }
              
            params = {
                'scope': 'openid session identity_customer',
                'prompt': 'NONE',
                'response_type': 'code',
                'state': state,
                'nonce': nonce,
                'client_id': 'mobiapp',
                'offline_token': account['offlineToken'],
                'login_hint': '%22DEVICE_TOKEN%3D' + account['deviceToken'] + '00A%22'
            }

            # Construct the URL with query parameters
            url = 'https://apigateway-prd.orange.pl/caap/caaptoken/v1/authorize'

            response = requests.post(get_full_url(url, params), headers=headers, json=body)

            # url https://apigateway-prd.orange.pl/caap/caaptoken/v1/token
            params = {
                'grant_type': 'execution_code',
                'code': response.json()['authenticationId'],
                'client_id': 'mobiapp',
                'state': response.json()['state']
            }

            response = requests.post(get_full_url('https://apigateway-prd.orange.pl/caap/caaptoken/v1/token', params), headers=headers, json={})

            # get tokens from response

            tokens = response.json()

            # print debug tokens
            if app.debug:
                print(tokens)

            access_token = tokens['access_token']

            # get account info
            response = requests.get(
                'https://apigateway-prd.orange.pl/moaaManagement/api/v1/customer/full?customerId=' + str(account['customerId']), headers={'Authorization': 'Bearer ' + access_token, **headers})

            # set account info to account_info variable
            account_info = response.json()

            # print debug account_info
            if app.debug:
                print(account_info)

            metric_accounts.labels(
                username=account['username'], customer_id=account_info['id']).set(1)

            # get billing accounts
            response = requests.get(
                'https://apigateway-prd.orange.pl/moaaManagement/api/v1/accounts?customerId=' + account_info['id'], headers={'Authorization': 'Bearer ' + access_token, **headers})

            # set billing accounts to billing_accounts variable
            billing_accounts = response.json()

            # print debug billing_accounts
            if app.debug:
                print(billing_accounts)

            # for each billing account in billing_accounts
            for billing_account in billing_accounts:
                metric_billing_accounts.labels(
                    username=account['username'], customer_id=account_info['id'], billing_account_type=billing_account['type'], billing_account_code=billing_account['code'], billing_account_name=billing_account['name']).set(1)
                # if billing account type is mobileprepaid
                if billing_account['type'] == 'mobileprepaid':
                    # get prepaid status
                    response = requests.get(
                        'https://apigateway-prd.orange.pl/wia/api/v1/account/status/' + billing_account['code'], headers={'Authorization': 'Bearer ' + access_token, **headers})

                    # set prepaid status to prepaid_status variable
                    prepaid_status = response.json()

                    # print debug prepaid_status
                    if app.debug:
                        print(prepaid_status)

                    # set prepaid expiry date metric
                    metric_prepaid_expiry_date.labels(
                        username=account['username'], customer_id=account_info['id'], billing_account_code=billing_account['code']).set(datetime.datetime.strptime(prepaid_status['accountExpiryDate'], '%Y-%m-%d %H:%M:%S').timestamp())

                    # set prepaid balance metrics for gc and pc
                    metric_prepaid_cash.labels(
                        username=account['username'], customer_id=account_info['id'], billing_account_code=billing_account['code'], cash_type='gc').set(int(prepaid_status['gc']['value']['amount'])/100)
                    # check if prepaid_status has key pc
                    if 'pc' in prepaid_status:
                        metric_prepaid_cash.labels(
                            username=account['username'], customer_id=account_info['id'], billing_account_code=billing_account['code'], cash_type='pc').set(int(prepaid_status['pc']['value']['amount'])/100)

                    # set prepaid data metrics for DATA and DATA_R
                    metric_prepaid_allowance_data.labels(
                        username=account['username'], customer_id=account_info['id'], billing_account_code=billing_account['code'], data_type='DATA').set(int(prepaid_status['fractions']['DATA']['sum']['amount']) * 1024)
                    metric_prepaid_allowance_data.labels(
                        username=account['username'], customer_id=account_info['id'], billing_account_code=billing_account['code'], data_type='DATA_R').set(int(prepaid_status['fractions']['DATA_R']['sum']['amount']) * 1024)

                    # for each item in prepaid_status['fractions']['DATA']['balances'] and prepaid_status['fractions']['DATA_R']['balances']
                    for item in [*prepaid_status['fractions']['DATA']['balances'], *prepaid_status['fractions']['DATA_R']['balances']]:
                        # set prepaid data item metric
                        metric_prepaid_allowance_data_item.labels(
                            username=account['username'], customer_id=account_info['id'], billing_account_code=billing_account['code'], data_type=item['type'], description=item['description']).set(int(item['value']['amount']) * 1024)
                        # set prepaid data item expiry date metric
                        metric_prepaid_allowance_data_item_expiry_date.labels(
                            username=account['username'], customer_id=account_info['id'], billing_account_code=billing_account['code'], data_type=item['type'], description=item['description']).set(datetime.datetime.strptime(item['expiryDate'], '%Y-%m-%d %H:%M:%S').timestamp())
        except Exception as e:
            print(e)


    return metrics_wsgi_app


if __name__ == '__main__':
    app.run('0.0.0.0', 5000)
