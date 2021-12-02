"""
- Fix CSS: Las imagenes de titulos mobile/desktop
- Push all Heladeras
----------------------
# Next
- Fix Shipping Rules Manuales por el momento
- Precio a las options
- Log: with open("log/initial_state.json", "w") as f: json.dump(initial_state, f)
- Fix SEO descriptions starts with: "OVERVIEW PRODUCT SNAPSHOT: ..."
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


def _get_body_html(soup):
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
    warranty = soup.select(f"{parent} > div:nth-child(6)")[0] if len(soup.select(f"{parent} > div:nth-child(6)")) > 0 else ''
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


def get_body_html(soup):
    # Fix anchors
    for a in soup.findAll("a"):
        a["href"] = f'https://www.bar-fridges-australia.com.au/{a["href"]}'
    # Fix images
    for img in soup.find_all("img"):
        try:
            img["src"] = f'https://www.bar-fridges-australia.com.au/{img["src"]}'
        except:
            continue

    body_html = []
    parent = soup.select("#bfa-vue-app > div > div:nth-child(2) > section > div > div > div")[0]
    for child in parent.findChildren("div", recursive=False):
        banner_img = child.find('img', {'class': 'product-guide-header-image-large'})
        if banner_img:
            section_title = banner_img['alt'].split('Bar Fridges Australia ')[1].split(' header')[0]
            if section_title in ['information', 'building in', 'warranty']:
                body_html.append(child.prettify())
    return ''.join(body_html)


    return parent

try:
    api = fetch()
    sku_tags = get_sku_tags()
    for x in api[4:10]:
        try:
            url = get_url(x["product_code"])
        except IndexError:
            print(f'❌ {x["product_code"]}')
            continue
        soup = BeautifulSoup(requests.get(url).content, "html.parser")
        initial_state = get_initial_state(soup)

        x["status"] = "active" if x["product_code"] in sku_tags else "draft"
        x["tags"] = (
            sku_tags[x["product_code"]]
            if x["product_code"] in sku_tags
            else "Bar Fridges Australia, All Bar Fridges"
        )

        # Options/Variants
        bfa_options = (
            initial_state["warranty_options"] + initial_state["product_options"]
        )
        # Options
        options = []
        for option in bfa_options:
            options.append(
                {
                    "name": option["option_name"],
                    "values": [
                        v["variant_name"] for _, v in option["variants"].items()
                    ][:3],
                }
            )

        # Variants
        combinations = []
        for option in bfa_options:
            variant = []
            for _, v in option["variants"].items():
                variant.append((v["modifier"], v["variant_name"]))
            combinations.append(variant)

        variants = []
        for count, combination in enumerate(list(itertools.product(*combinations))):
            aditional = sum([float(i[0]) for i in combination])
            titles = [i[1].strip(" ") for i in combination]
            variants.append(
                {
                    "title": " / ".join(titles),
                    "sku": f'{x["product_code"]}-{count}',
                    "price": int(x["price"]) + int(aditional),
                    "weight": x["weight"],
                    "inventory_quantity": int(initial_state["quantity"]),
                    "option1": titles[0] if len(titles) > 0 else None,
                    "option2": titles[1] if len(titles) > 1 else None,
                    "option3": titles[2] if len(titles) > 2 else None,
                    "taxable": False,
                    "inventory_policy": "deny",
                    "compare_at_price": None,
                    "fulfillment_service": "manual",
                    "inventory_management": "shopify",
                    "barcode": "",
                    "image_id": None,
                    "weight_unit": "kg",
                    "requires_shipping": True,
                }
            )

        body_html = get_body_html(soup)

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
                    "body_html": body_html,
                    "metafields": [
                        {
                            "namespace": "source",
                            "key": "url",
                            "value": url,
                            "value_type": "string",
                        },
                        {
                            "namespace": "source",
                            "key": "product_id",
                            "value": x["product_id"],
                            "value_type": "string",
                        },
                        {
                            "namespace": "dimensions",
                            "key": "depth",
                            "value": int(x["depth"]),
                            "value_type": "integer",
                        },
                        {
                            "namespace": "dimensions",
                            "key": "height",
                            "value": int(x["height"]),
                            "value_type": "integer",
                        },
                        {
                            "namespace": "dimensions",
                            "key": "width",
                            "value": int(x["width"]),
                            "value_type": "integer",
                        },
                    ],
                }
            },
        ).json()["product"]
        print(f"🔗 https://thebigdino.myshopify.com/admin/products/{p['id']}")
        # ).json(); print(p)

except KeyboardInterrupt:
    pass
