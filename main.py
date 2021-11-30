"""
- Log
    with open("log/initial_state.json", "w") as f:
        json.dump(initial_state, f)
- Options / Variants
- Fix SEO descriptions starts with: "OVERVIEW PRODUCT SNAPSHOT: ..."
- Replace Images for <h1>Info / Building In/ warranty 
- Push Heladeras
- (Add from data/urls)
"""
import csv
import json
import itertools
from dotenv import dotenv_values
import requests
from requests.models import HTTPBasicAuth
from bs4 import BeautifulSoup

SECRETS = dotenv_values(".env")
ROOT = SECRETS["SHOPIFY_URL"]


def fetch():
    endpoint = SECRETS["BAR_FRIDGES_AUSTRALIA_ENDPOINT"]
    username = SECRETS["BAR_FRIDGES_AUSTRALIA_USERNAME"]
    password = SECRETS["BAR_FRIDGES_AUSTRALIA_PASSWORD"]
    r = requests.get(endpoint, auth=HTTPBasicAuth(username, password))
    active = [x for x in r.json() if x["active"]]
    return active


def get_sku_tags():
    """Returns Dict SKU: TAGS"""
    with open("data/sku-tags.csv") as csvfile:
        reader = csv.DictReader(csvfile)
        sku_tags = {}
        for row in reader:
            sku = row["SKU"]
            tags = row["TAGS"]
            sku_tags[sku] = tags
        return sku_tags


def get_url(sku):
    api_key = SECRETS["SEARCHANISE_API_KEY"]
    url = f"https://www.searchanise.com/getwidgets?api_key={api_key}&maxResults=100&q={sku}"
    r = requests.get(url)
    items = r.json()["items"]
    result = list(
        filter(lambda x: x["product_code"] == sku and int(x["quantity"]) >= 0, items)
    )[0]

    return result["link"]


def get_body_html(soup):
    for a in soup.findAll("a"):
        a["href"] = f'https://www.bar-fridges-australia.com.au/{a["href"]}'
    for img in soup.find_all("img"):
        try:
            img["src"] = f'https://www.bar-fridges-australia.com.au/{img["src"]}'
        except:
            continue
    parent = "#bfa-vue-app > div > div:nth-child(2) > section > div > div > div"
    info = soup.select(f"{parent} > div:nth-child(2)")[0]
    installation = soup.select(f"{parent} > div:nth-child(4)")[0]
    warranty = soup.select(f"{parent} > div:nth-child(6)")[0]

    return f"{info}\n{installation}\n{warranty}"


def get_initial_state(soup):
    raw = soup.find("script").string.strip()
    data = raw.split("window.__INITIAL_STATE__ = ")[1].split(";\n")[0]
    parsed = json.loads(data)
    initial_state = parsed["products_view_extended_product"]
    return initial_state


def calculate_cost(price):
    price = float(price)
    margin = 12
    difference = price * margin * 0.01
    return price - difference


def add_metadata(p, value_type, namespace, key, value):
    r = requests.put(
        url=f'{ROOT}/products/{p["id"]}.json',
        headers={"Content-Type": "application/json"},
        json={
            "product": {
                "id": p["id"],
                "metafields": [
                    {
                        "namespace": namespace,
                        "key": key,
                        "value": value,
                        "value_type": value_type,
                    }
                ],
            }
        },
    )


def get_options(initial_state):
    w = initial_state["warranty_options"][0]
    return [
        {
            "position": 1,
            "name": w["option_name"],
            "values": [w["variants"][v]["variant_name"] for v in w["variants"]][:3],
        }
    ]


try:
    api = fetch()
    sku_tags = get_sku_tags()
    for x in api[4:]:
        url = get_url(x["product_code"])
        soup = BeautifulSoup(requests.get(url).content, "html.parser")
        initial_state = get_initial_state(soup)

        x["status"] = "active" if x["product_code"] in sku_tags else "draft"
        x["tags"] = (
            sku_tags[x["product_code"]]
            if x["product_code"] in sku_tags
            else "Bar Fridges Australia, All Bar Fridges"
        )

        options = []
        for option in (
            initial_state["warranty_options"] + initial_state["product_options"]
        ):
            options.append(
                {
                    "name": option["option_name"],
                    "values": [
                        v["variant_name"] for _, v in option["variants"].items()
                    ][:3],
                }
            )

        variants = []
        combinations = list(itertools.product(*[o["values"] for o in options]))
        for count, combination in enumerate(combinations):
            variants.append(
                {
                    "title": combination,
                    "price": int(x["price"]) + count,
                    "sku": f'{x["product_code"]}-{count}',
                    "inventory_policy": "deny",
                    "compare_at_price": None,
                    "fulfillment_service": "manual",
                    "inventory_management": "shopify",
                    "option1": combination[0] if len(combination) > 0 else None,
                    "option2": combination[1] if len(combination) > 1 else None,
                    "option3": combination[2] if len(combination) > 2 else None,
                    "taxable": False,
                    "barcode": "",
                    "image_id": None,
                    "weight": x["weight"],
                    "weight_unit": "kg",
                    "inventory_quantity": int(initial_state["quantity"]),
                    "requires_shipping": True,
                }
            )
        # variants.append({
        #     "title": options[0]["name"],
        #     "price": x["price"],
        #     "sku": f'{x["product_code"]}',
        #     # "position": 1,
        #     "inventory_policy": "deny",
        #     "compare_at_price": None,
        #     "fulfillment_service": "manual",
        #     "inventory_management": "shopify",
        #     "option1": options[0]["values"][0],
        #     "option2": None,
        #     "option3": None,
        #     "taxable": False,
        #     "barcode": "",
        #     "image_id": None,
        #     "weight": x["weight"],
        #     "weight_unit": "kg",
        #     "inventory_quantity": int(initial_state["quantity"]),
        #     "requires_shipping": True,
        # })

        # Create Product
        p = requests.post(
            url=f"{ROOT}/products.json",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={
                "product": {
                    # Harcoded
                    "product_type": "Refrigerator",
                    "template_suffix": "barfridgesaustralia",
                    # Read
                    "status": x["status"],
                    "tags": x["tags"],
                    "title": x["product_name"],
                    "vendor": x["brand"],
                    "images": [{"src": i} for i in x["product_images"]],
                    # Calculated
                    "options": options,
                    "variants": variants,
                    "body_html": get_body_html(soup),
                }
            },
        ).json()["product"]
        print(f"🔗 https://thebigdino.myshopify.com/admin/products/{p['id']}")

        """
        # Add metafields
        add_metadata(p, "string", "source", "url", url)
        add_metadata(p, "string", "source", "product_id", x["product_id"])
        add_metadata(p, "integer", "dimensions", "depth", x["depth"])
        add_metadata(p, "integer", "dimensions", "height", x["height"])
        add_metadata(p, "integer", "dimensions", "width", x["width"])
        # done!
        """

except KeyboardInterrupt:
    pass
