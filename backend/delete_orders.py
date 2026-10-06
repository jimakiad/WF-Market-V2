"""Delete only matching sell orders belonging to the authenticated account."""
import requests
from get_orders import get_orders
from wfm_client import api_request, auth_headers


def delete_matching_orders(token, api_url, mods_data):
    augment_ids = {mod['id'] for mods in mods_data.values() for mod in mods if mod.get('id')}
    orders = get_orders(token, api_url)['data']
    matching = [order for order in orders
                if order.get('type') == 'sell' and order.get('itemId') in augment_ids]
    result = {'deleted': 0, 'skipped': len(orders) - len(matching), 'failed': [], 'unprocessed': 0}
    for index, order in enumerate(matching):
        try:
            api_request('DELETE', f"{api_url}/v2/order/{order['id']}", headers=auth_headers(token))
            result['deleted'] += 1
        except requests.RequestException:
            result['failed'].append(order['itemId'])
            result['unprocessed'] = len(matching) - index - 1
            break
    return result
