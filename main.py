import os
from dotenv import load_dotenv
import json
from get_all_items import get_all_items as func_get_all_items
from get_orders import get_orders as func_get_orders
from scrape_syndicate_mods import scrape_syndicate_mods
from login import login
from create_orders import create_orders
from delete_orders import delete_matching_orders

load_dotenv()

WFM_API = os.getenv("WFM_API")
LOGIN_CREDENTIALS= {"User_Name": os.getenv("WFM_USER_EMAIL"), "Password": os.getenv("WFM_USER_PASSWORD")}

if not all([WFM_API, os.getenv("WFM_USER_EMAIL"), os.getenv("WFM_USER_PASSWORD")]):
    raise RuntimeError("Missing required environment variables")

def main():
    JWT = login(LOGIN_CREDENTIALS["User_Name"], LOGIN_CREDENTIALS["Password"],WFM_API)[1]
    #print(JWT)
    if not JWT:
        print("Failed to login")
        return
    
    #Parse all items
    items_data = func_get_all_items(JWT,WFM_API)
    with open('items.json', 'w', encoding='utf-8') as f:
        json.dump(items_data, f, indent=4)
    #print("Items data saved to items.json")
    
    #Parse all user orders
    orders_data = func_get_orders(JWT,WFM_API)
    with open('orders.json', 'w', encoding='utf-8') as f:
        json.dump(orders_data, f, indent=4)
    #print("Orders data saved to orders.json")
    
    # Renew Augments
    """
    renew_augment_list = input("Would you like to renew the augment list? Y/n")
    while renew_augment_list != "Y" and renew_augment_list != "n":
        print(renew_augment_list)
        renew_augment_list = input("Would you like to renew the augment list? Y/n")
        
    match renew_augment_list:
        case "Y": 
            scrape_syndicate_mods()
        case "n":
            print("Application may malfunction if new mods are added since last renewal.")
    """
    scrape_syndicate_mods()
    delete_matching_orders (JWT,WFM_API)       
    create_orders(JWT,WFM_API)
    
    
main()
    