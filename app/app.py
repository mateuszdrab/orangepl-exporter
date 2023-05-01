from flask import Flask, jsonify, request
from prometheus_client import Counter, Gauge, generate_latest, make_wsgi_app
from prometheus_flask_exporter import PrometheusMetrics
import json
import requests
import datetime

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
        # login_body variable is a dictionary with login and password from account variable
        login_body = {'username': account['username'],
                      'password': account['password'],
                      'grant_type': 'password',
                      'scope': 'offline_access',
                      'client_id': x_api_key,
                      #   'phone_model': 'iPhone'
                      }

        headers = {
            # 'X-OPL-AppVersion':     '5.72.0.11207',
            'X-Api-Key':            x_api_key,
            # 'User-Agent':           'M % C3 % B3j % 20Orange/11207 CFNetwork/1404.0.5 Darwin/22.3.0',
            'X-OPL-Platform':       'iOS',
            'X-OPL-RequestSource':  'mobiapp'
        }

        # post request to  https://apiint.orange.pl/app/oauth/v2/token with body as form-data and headers as headers appended to www-form-urlencoded content type header
        response = requests.post(
            'https://apiint.orange.pl/app/oauth/v2/token', data=login_body, headers={'Content-Type': 'application/x-www-form-urlencoded', **headers})

        # get access_token from response
        access_token = response.json()['access_token']

        # print access_token if debug is enabled
        if app.debug:
            print(access_token)

        # get account info from /app/oauth/v2/authInfo endpoint using access_token
        response = requests.get(
            'https://apiint.orange.pl/app/oauth/v2/authInfo', headers={'Authorization': 'Bearer ' + access_token, **headers})

        # set account info to account_info variable
        account_info = response.json()

        # print debug account_info
        if app.debug:
            print(account_info)

        metric_accounts.labels(
            username=account['username'], customer_id=account_info['customerId']).set(1)

        # get billing accounts from /billingManagement/v2/billingAccounts/briefs?customerId=
        response = requests.get(
            'https://apiint.orange.pl/billingManagement/v2/billingAccounts/briefs?customerId=' + account_info['customerId'], headers={'Authorization': 'Bearer ' + access_token, **headers})

        # set billing accounts to billing_accounts variable
        billing_accounts = response.json()

        # print debug billing_accounts
        if app.debug:
            print(billing_accounts)

        # for each billing account in billing_accounts
        for billing_account in billing_accounts:
            metric_billing_accounts.labels(
                username=account['username'], customer_id=account_info['customerId'], billing_account_type=billing_account['billingAccountType'], billing_account_code=billing_account['billingAccountCode'], billing_account_name=billing_account['billingAccountName']).set(1)
            # if billing account type is mobileprepaid
            if billing_account['billingAccountType'] == 'mobileprepaid':
                # get prepaid status from /prepaid/v1/status/{billingAccountCode}
                response = requests.get(
                    'https://apiint.orange.pl/prepaid/v1/status/' + billing_account['billingAccountCode'], headers={'Authorization': 'Bearer ' + access_token, **headers})

                # set prepaid status to prepaid_status variable
                prepaid_status = response.json()

                # print debug prepaid_status
                if app.debug:
                    print(prepaid_status)

                # set prepaid expiry date metric
                metric_prepaid_expiry_date.labels(
                    username=account['username'], customer_id=account_info['customerId'], billing_account_code=billing_account['billingAccountCode']).set(datetime.datetime.strptime(prepaid_status['accountExpiryDate'], '%Y-%m-%d %H:%M:%S').timestamp())

                # set prepaid balance metrics for gc and pc
                metric_prepaid_cash.labels(
                    username=account['username'], customer_id=account_info['customerId'], billing_account_code=billing_account['billingAccountCode'], cash_type='gc').set(int(prepaid_status['gc']['value']['amount'])/100)
                # check if prepaid_status has key pc
                if 'pc' in prepaid_status:
                    metric_prepaid_cash.labels(
                        username=account['username'], customer_id=account_info['customerId'], billing_account_code=billing_account['billingAccountCode'], cash_type='pc').set(int(prepaid_status['pc']['value']['amount'])/100)

                # set prepaid data metrics for DATA and DATA_R
                metric_prepaid_allowance_data.labels(
                    username=account['username'], customer_id=account_info['customerId'], billing_account_code=billing_account['billingAccountCode'], data_type='DATA').set(int(prepaid_status['fractions']['DATA']['sum']['amount']) * 1024)
                metric_prepaid_allowance_data.labels(
                    username=account['username'], customer_id=account_info['customerId'], billing_account_code=billing_account['billingAccountCode'], data_type='DATA_R').set(int(prepaid_status['fractions']['DATA_R']['sum']['amount']) * 1024)

                # for each item in prepaid_status['fractions']['DATA']['balances'] and prepaid_status['fractions']['DATA_R']['balances']
                for item in [*prepaid_status['fractions']['DATA']['balances'], *prepaid_status['fractions']['DATA_R']['balances']]:
                    # set prepaid data item metric
                    metric_prepaid_allowance_data_item.labels(
                        username=account['username'], customer_id=account_info['customerId'], billing_account_code=billing_account['billingAccountCode'], data_type=item['type'], description=item['description']).set(int(item['value']['amount']) * 1024)
                    # set prepaid data item expiry date metric
                    metric_prepaid_allowance_data_item_expiry_date.labels(
                        username=account['username'], customer_id=account_info['customerId'], billing_account_code=billing_account['billingAccountCode'], data_type=item['type'], description=item['description']).set(datetime.datetime.strptime(item['expiryDate'], '%Y-%m-%d %H:%M:%S').timestamp())

    return metrics_wsgi_app


if __name__ == '__main__':
    app.run('0.0.0.0', 5000)
