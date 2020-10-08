import asyncio
import json
import random
import re
import string
import time
import traceback as tb
import aiohttp
from bs4 import BeautifulSoup

import conf
import discord
import logger
import util

webhook = conf.webhook

screen_logger = logger.make(name='supplystore_logger', filename='supplystore.logs')


# todo set max redirects
class invalid_status_code(Exception):
    """exception if status code is not 200 or 404"""


class proxy_blocked_by_security(Exception):
    """ when a proxy is blocked by website antibot"""


def raise_for_status(response):
    if not (response.status_code == 200 or response.status_code == 404):
        raise invalid_status_code('{} -> {}'.format(response.url, response.status_code))

    if 'This website is using a security service to protect itself from online attacks' in response.content:
        raise proxy_blocked_by_security('{} -> {}'.format(response.url, response.status_code))


def log_based_on_response(id, response):
    cache_status = response.headers['x-cache'].split(" ")[0] if 'x-cache' in response.headers else "No-Cache-Status"

    screen_logger.info("{} > {} -> {} -> {}".format(id, str(response.url), response.status_code, cache_status))


def log_exception(id, ex, traceback=False):
    if traceback:
        trace_str = "\n".join(tb.format_tb(ex.__traceback__))
        screen_logger.info("{} > {}\n{}".format(id, trace_str, str(ex)))
    else:
        screen_logger.info("{} > {}".format(id, str(ex)))


def _async_fetcher_boilerplate(*, raise_exceptions=True, traceback=True, log=True):
    def wrapper(function):
        async def inner_wrapper(self, *args, **kwargs):

            if self.current_proxy is None:
                await self.change_proxy(log=log)

            try:

                return await function(self, *args, **kwargs)
            except Exception as e:

                log_exception(self.id, e, traceback=traceback)
                await self.change_proxy(log=log)

                if raise_exceptions:
                    raise

        return inner_wrapper

    return wrapper


class Searcher:
    def __init__(self, *, id, proxy_buffer):
        self.proxy_buffer = proxy_buffer
        self.id = id
        self.current_proxy = None

    @staticmethod
    def parse_product_info_from_url(html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        products = soup.select('ul.collection-grid-content li')
        results = []

        for product in products:
            image_url = product.select_one('a img')['src']
            title = product.select_one('a img')['alt']
            url = product.select_one('a')['href']
            result = {
                'title': title,
                'image_url': image_url,
                'url': url
            }
            results.append(result)
        return results

    @staticmethod
    def get_total_page_number_from_url(html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        page_numbers = soup.select('div#pagenation a')
        return len(page_numbers) + 1

    async def get_prod_info_by_url(self, *, session, url):

        response = await util.products_get(
            f"{url}", self.current_proxy
        )

        log_based_on_response(self.id, response)

        result = []
        if response.status_code != 404:
            result = Searcher.parse_product_info_from_url(response.content)
        else:
            await self.change_proxy()
        return result

    async def change_proxy(self, *, log=False):
        self.current_proxy = await self.proxy_buffer.get_and_inc()
        if log:
            screen_logger.info(f"{self.id} > Using Proxy {self.current_proxy}")

    @_async_fetcher_boilerplate(raise_exceptions=True, traceback=False, log=True)
    async def get_prods_by_query(self, **kwargs):
        prod_details, total_pages = await self._get_products_by_query_for_page(page=1, return_page_num=True, **kwargs)

        if total_pages > 1:
            for sub_pages in util.grouper(range(total_pages), 5):
                details = await asyncio.gather(
                    *[self._get_products_by_query_for_page(page=page, **kwargs) for page in sub_pages if page])

                for detail in details:
                    prod_details.extend(detail)

        return prod_details

    @_async_fetcher_boilerplate(raise_exceptions=True, traceback=False, log=True)
    async def get_prods_by_urls(self, *, urls, **kwargs):
        prod_details = await asyncio.gather(*[self.get_prod_info_by_url(url=url, **kwargs) for url in urls])

        return prod_details


class ProductManager:
    __previous_proudcts = []
    __temp_stock = []
    __is_first_time = True

    def __init__(self, id, session, max_workers):
        self.id = id
        self.session = session
        self.embed_sender = discord.embedSender(webhook=webhook, session=session)
        self.max_workers = max_workers
        self.restock_sending_time = {}
        self.time_bw_notification_in_seconds = conf.time_bw_notification_in_seconds

    def log_updated(self, product):
        if product:
            screen_logger.info(f"{self.id} > Found added Item: ")
            screen_logger.info("{} > {}".format(self.id, product['url']))
            screen_logger.info("{} > {}".format(self.id, product['title']))

    def check_if_updated(self, product):
        if self.__is_first_time:
            return False

        is_new = True
        for item in self.__previous_proudcts:
            if item['url'] == product['url'] and item['title'].lower().strip() == product['title'].lower().strip():
                is_new = False
                break
        if is_new:
            return True

        return False

    def update_stock(self, new_products):
        self.__previous_proudcts = new_products
        screen_logger.info("{} > Products:  {}".format(self.id, self.__previous_proudcts))
        if self.__is_first_time:
            self.__is_first_time = False

    async def send_embed(self, *, url, embed, log=False):
        result = await self.embed_sender.send(embed)
        if log:
            if result:
                screen_logger.info("{} > **Discord Notification Sent for {}**".format(self.id, url))
            else:
                screen_logger.info("{} > **Discord Notification Failed for {}**".format(self.id, url))

    def send_updated(self, *, prod, last_page):
        if not self.__is_first_time:
            screen_logger.info("{} > Detected Products: {}".format(self.id, len(prod)))
        updated_count = 0
        for item in prod:
            if self.check_if_updated(item):
                self.log_updated(item)
                embed = discord.make_embed(item)
                url = item['url']
                now = time.time()
                self.restock_sending_time[url] = now
                asyncio.ensure_future(self.send_embed(url=item['url'], embed=embed, log=True))
                updated_count += 1
        if not self.__is_first_time:
            screen_logger.info("{} > Added Products:  {}".format(self.id, updated_count))
        self.__temp_stock.extend(prod)
        if last_page:
            self.update_stock(self.__temp_stock)
            self.__temp_stock = []

    def send_notification(self, last_page, *prods):
        for prod in prods:
            if prod:
                self.send_updated(prod=prod, last_page=last_page)


class Monitor:
    __sold_out_urls = []

    def __init__(self, queries, proxy_buffer, *, query_workers, url_workers, notification_senders, urls):
        self.queries = queries
        self.proxy_buffer = proxy_buffer
        self.query_workers = query_workers
        self.url_workers = url_workers
        self.notification_senders = notification_senders
        self.urls = urls

        self.temp_stock = {}

    def _init_session(self):
        timeout = aiohttp.ClientTimeout(total=10)

        return aiohttp.ClientSession(timeout=timeout)

    async def _monitor_query_step(self, *, query_worker, **kwargs):
        prods = await query_worker.get_prods_by_query(**kwargs)

        if isinstance(prods, list):
            prods = [prod['url'] for prod in prods if prod]

            return prods

    async def process_url(self, *, worker, session, product_manager, url, last_page):

        try:
            products = await worker.get_prods_by_urls(session=session, urls=[url])

            for product in products:
                if len(product) == 0:
                    screen_logger.info('query-notification-sender > Detected Products: 0')
                if product is not None:
                    product_manager.send_notification(last_page, product)

        except Exception as e:
            pass

    async def _monitor(self, *, session, wait_time):


        query_workers = [Searcher(id=f'query-worker-{i}', proxy_buffer=self.proxy_buffer) for i in
                         range(self.query_workers)]

        url_workers = [Searcher(id=f'url-worker-{i}', proxy_buffer=self.proxy_buffer) for i in range(self.url_workers)]

        product_manager = ProductManager(id='query-notification-sender', session=session,max_workers=self.notification_senders)

        # new_arrival = "https://www.supplystore.com.au/brands/new-arrivals/c-28/c-150"
        # response = await self.process_url(session)
        # page_numbers = Searcher.get_total_page_number_from_url(response.content)
        # for item in range(1, 12):
        #     self.urls.append(new_arrival + '?p=' + str(item))

        while True:
            try:
                screen_logger.info('___Monitor Start___')
                last_page = False
                for i, url in enumerate(self.urls):
                    screen_logger.info('Page Url: {}'.format(url))

                    if i + 1 == len(self.urls):
                        last_page = True
                    coros = [self.process_url(session=session, url=url, product_manager=product_manager,
                                              worker=worker, last_page=last_page) for worker in query_workers]
                    await asyncio.gather(*coros)

                await asyncio.sleep(wait_time)

            except Exception as e:
                log_exception('Query-Monitor-Main', e, traceback=True)

    async def monitor(self, *, wait_time):
        async with self._init_session() as session:
            await self._monitor(session=session, wait_time=wait_time)


async def main(queries, proxies, urls, query_workers, url_workers, notification_senders, wait_time):

    proxy_buffer = util.readOnlyAsyncCircularBuffer(proxies)

    monitor = Monitor(queries, proxy_buffer, query_workers=query_workers, url_workers=url_workers,
                      notification_senders=notification_senders, urls=urls)
    await monitor.monitor(wait_time=wait_time)


if __name__ == "__main__":
    queries = util.nonblank_lines(conf.query_file)
    proxies = util.load_proxies_from_file(conf.proxy_file, shuffle=True)
    urls = util.nonblank_lines(conf.url_file)
    asyncio.run(
        main(queries, proxies, urls, conf.query_workers, conf.url_workers, conf.notification_senders, conf.wait_time))
