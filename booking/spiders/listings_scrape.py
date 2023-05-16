import scrapy
from urllib.parse import urlencode
import json
import re

from booking.items import ListingItem, RoomItem


class ListingsScrapeSpider(scrapy.Spider):
    name = "listings_scrape"
    allowed_domains = ["www.booking.com"]
    params = {
        'ss': 'Praha',
        'dest_type': 'city',
        # 'checkin': '2023-06-05',
        # 'checkout': '2023-06-10',
        'group_adults': 1,
        'group_children': 0,
        # 'ltfd': '1:5:6-2023_8-2023_11-2023:1',
        'no_rooms': 1,
    }

    base = "https://www.booking.com/searchresults.cs.html?"
    start_urls = [base + urlencode(params)]

    def parse(self, response):
        yield from self.parse_page(response)
        for i in range(1, int(response.xpath('//li/button/text()').get())):
            self.params['offset'] = i * 25
            yield scrapy.Request(self.basis + urlencode(self.params), callback=self.parse_page)
       
    def parse_page(self, response):
        yield from response.follow_all(css="h3 a", callback=self.parse_listing)

    def parse_listing(self, response):
        listing = ListingItem()

        js = json.loads(response.css("script[id$='SafetyDesktop'] + script::text").get())
        listing['name'] = js['HotelTranslation:{}']['name']
        listing['seoDescription'] = js['HotelTranslation:{}']['description']

        # 'a' is a name for a temporary variable, it doesn't serve any purpose - it's just here for convenience
        a = response.css("link[rel='alternate'][href^='a']").attrib(['href'])
        listing['id'] = a[a.rfind('/')+1:a.find('?')]

        listing['address'] = response.css("span.hp_address_subtitle::text").get().replace("\n", "")
        listing['photos']: list[str] = re.findall("large_url: '([^']+)'", response.css("script[type='application/ld+json'] + script::text").get())

        for room_id in response.xpath(
            "//div[@class='room-lightbox-container js-async-room-lightbox-container']/@data-room-id"
            ).getall():
            yield scrapy.Request("https://www.booking.com/fragment.en.json", self.parse_room,
                                 method="POST", body={
                                    'name': 'room.lightbox',
                                    'room_id': room_id,
                                    'hotel_id': listing['id'],
                                }, cb_kwargs={'listing': listing})


    def parse_room(self, response, listing):
        item = RoomItem()