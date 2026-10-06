"""Create orders from this account's live listings, without shared user files."""
import requests
from get_orders import get_orders
from wfm_client import api_request, auth_headers


def create_orders(token, api_url, mods_data, syndicates, platinum):
    orders = get_orders(token, api_url)['data']
    listed = {order['itemId'] for order in orders if order.get('type') == 'sell'}
    selected = {
        mod['id']: mod['Name'] for syndicate in syndicates
        for mod in mods_data[syndicate] if mod.get('id')
    }
    result = {'created': 0, 'skipped': 0, 'failed': [], 'unprocessed': 0}
    for index, (item_id, name) in enumerate(selected.items()):
        if item_id in listed:
            result['skipped'] += 1
            continue
        try:
            api_request('POST', f'{api_url}/v2/order', headers=auth_headers(token), json={
                'itemId': item_id, 'type': 'sell', 'platinum': platinum,
                'quantity': 1, 'visible': True, 'rank': 0,
            })
            result['created'] += 1
        except requests.RequestException:
            # A timed-out write may have succeeded. Never automatically retry it.
            result['failed'].append(name)
            result['unprocessed'] = len(selected) - index - 1
            break
    return result
