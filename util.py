import asyncio
import random
import ssl
import requests


def nonblank_lines(filename):
    with open(filename) as f:
        stripped_lines = [line.strip() for line in f]
        return [line for line in stripped_lines if line]


def load_proxies_from_file(filename, shuffle=True):
    proxies = nonblank_lines(filename)

    if shuffle:
        random.shuffle(proxies)
    result = []

    for proxy in proxies:
        proxyTokens = proxy.split(':')

        proxyStr = ":".join(proxyTokens[0:2])

        if len(proxyTokens) == 4:
            proxyStr = ":".join(proxyTokens[2:]) + "@" + proxyStr

        result.append({'http': 'http://' + proxyStr, 'https': 'https://' + proxyStr})
    return result


class readOnlyAsyncCircularBuffer:
    def __init__(self, data):
        assert len(data) > 0
        self.data = list(data)
        self.lock = asyncio.Lock()
        self.index = 0

    async def get(self):
        async with self.lock:
            return self.data[self.index]

    async def get_and_inc(self):
        async with self.lock:
            oIndex = self.index
            self.index = (self.index + 1) % len(self.data)
            return self.data[oIndex]


ctx = ssl.SSLContext(protocol=ssl.PROTOCOL_TLSv1_2)

cipher = [
    'ECDHE-ECDSA-AES128-GCM-SHA256', 'ECDHE-ECDSA-AES256-GCM-SHA384', 'ECDHE-RSA-AES256-GCM-SHA384',
    'ECDHE-RSA-AES128-GCM-SHA256', 'ECDHE-ECDSA-AES256-SHA384', 'ECDHE-ECDSA-AES128-SHA256', 'ECDHE-RSA-AES256-SHA384',
    'ECDHE-RSA-AES128-SHA256', 'ECDHE-ECDSA-AES256-SHA', 'ECDHE-ECDSA-AES128-SHA', 'ECDHE-RSA-AES256-SHA',
    'ECDHE-RSA-AES128-SHA', 'AES256-GCM-SHA384', 'AES128-GCM-SHA256', 'AES256-SHA256', 'AES128-SHA256', 'AES256-SHA',
    'AES128-SHA', 'DES-CBC3-SHA'
]

ctx.set_ciphers(" ".join(cipher))


async def safe_get(session, *args, **kwargs):
    version = random.randint(71, 75)
    os = random.sample(['10', '8.0', '8.1', '6.1'], 1)[0]

    headers = {
        "Host": "www.supplystore.com.au",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": f"Mozilla/5.0 (Windows NT {os}.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.3729.131 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
        "Accept-Encoding": "deflate, gzip",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8"
    }

    async with session.get(*args, headers=headers, ssl=ctx, **kwargs) as response:
        response.content = await response.text()

    return response


async def products_get(url, current_proxy):
    return requests.get(url)
