import asyncio
from datetime import datetime

import util

def make_embed(details):
    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%d %H:%M:%S")
    image_url = details['image_url']
    domain = ['http', 'https']
    if not any((c in domain) for c in image_url):
        image_url = 'https://supplystore.com.au' + details['image_url']

    return [{
        'title': "{}\n".format(details['title']),
        'url': 'https://www.supplystore.com.au' + details['url'],
        'color': 8522486,
        'thumbnail': {
          'url': image_url
        },
        'fields': [
            {
                'name': 'Type ',
                'value': 'New Add',
                'inline': True
            },
            {
                'name': "Site",
                'value': 'Supply Store',
                'inline': True

            }
        ],
        'footer': {
            'icon_url': 'https://media.discordapp.net/attachments/698693055435243570/717667576884363284/image0_23.png',
            'text': 'Amenity Monitors:->' + dt_string
        }
    }]

def make_sold_out(url):
    return [{
        'title': 'This product sold out',
        'fields': [
            {
                'name': "Product Url",
                'value': url,
            },
        ],
        'color': 0xee0000,
        'footer': {
            'icon_url': '',
            'text': 'Amenity Monitors'
        }
    }]

def make_restocked(url):
    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%d %H:%M:%S")
    return [{
        'title': 'This product restocked',
        'fields': [
            {
                'name': 'Type ',
                'value': 'New Add',
                'inline': True
            },
            {
                'name': "Product Url",
                'value': url,
                'inline': True
            },
        ],
        'color': 0x0000dd,
        'footer': {
            'icon_url': 'https://media.discordapp.net/attachments/698693055435243570/717667576884363284/image0_23.png',
            'text': 'Amenity Monitors' + dt_string
        }
    }]

class embedSender:
    def __init__(self, *, session, webhook, wait_time_on_error=4):
        self.webhook = webhook
        self.session = session
        self.wait_time_on_error = wait_time_on_error

    async def send(self, embed):
        data = {
            'embeds': embed
        }
        for _ in range(2):
            async with self.session.post(self.webhook, json=data) as resp:
                if resp.status == 204:
                    break

            await asyncio.sleep(self.wait_time_on_error)
        return resp.status == 204
