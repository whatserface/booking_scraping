import scrapy
from urllib.parse import urlencode
import json
import re
from scrapy import Request, FormRequest

from booking.items import ListingItem, RoomItem, RoomFacilityItem, PhotoItem


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
    headers = {}
    cookies = {}
    categories_list = []

    base = "https://www.booking.com/searchresults.cs.html?"
    start_urls = [base + urlencode(params)]

    def parse(self, response):
        yield from self.parse_page(response)
        for i in range(1, int(response.xpath('//li/button/text()').get())):
            self.params['offset'] = i * 25
            yield Request(self.basis + urlencode(self.params), callback=self.parse_page)
       
    def parse_page(self, response):
        yield from response.follow_all(css="h3 a", callback=self.parse_listing)

    def parse_listing(self, response):
        listing = ListingItem()

        js = json.loads(response.css("script[id$='SafetyDesktop'] + script::text").get())
        listing['name'] = js['HotelTranslation:{}']['name']
        listing['seoDescription'] = js['HotelTranslation:{}']['description']
        listing['languagesSpoken'] = js['PropertyPageFullExtendedAdamQueryResult:{}']['languagesSpoken']['languageCodes']
        listing['coordinates'] = js[js['PropertyPageFullExtendedAdamQueryResult:{}']['basicPropertyData']]['location']
        listing['coordinates'].pop('__typename', None)
        listing['coordinates'].pop('city', None)

        self.headers['x-booking-csrf'] = re.findall("'X-Booking-CSRF': '([^']+)'",
                response.xpath(
                    "//script[@class='jquery-script-tag']/preceding-sibling::script[position() < 3]/text()"
                )[0].get())[0]
        a = response.headers['Set-Cookie']
        self.cookies['bkng'] = a[(pos := a.find(b'bkng=')+5):a.find(b'; ', pos)]

        listing['id'] = response.xpath("//input[@name='hotel_id']/@value").get()

        listing['address'] = response.css("span.hp_address_subtitle::text").get().replace("\n", "")
        # TODO: change regex pattern to (?<=hotelPhotos: )(.|\n|\r)+(?=,\nb_hotelfeaturedreviews_url)
        # Then parse a dirty json as shown in xren.js example
        listing['photos']: list[str] = list(set(re.findall("highres_url: '([^']+)'", response.css("script[type='application/ld+json'] + script::text").get())))

        timebar = response.xpath('//span[@data-component="prc/timebar"]')
        listing['check_in'], listing['check_out'] = timebar
        listing['check_in'] = [timebar[0].attrib['data-from'], timebar[0].attrib.get('data-until', '')]
        listing['check_out'] = [timebar[1].attrib.get('data-from', ''), timebar[1].attrib['data-until']]

        self.categories_list = json.loads(response.css(
            'script[id="__CAPLA_CHUNK_METADATA__b-property-web-property-pageNTTNcUeH/PropertyHealthSafetyDesktop"]::text')
            .get())["copyTags"]["facilitytype/name"]["items"]

        for room_id in response.xpath(
            "//div[@class='room-lightbox-container js-async-room-lightbox-container']/@data-room-id"
            ).getall():
            yield FormRequest("https://www.booking.com/fragment.en-gb.json", self.parse_room,
                                    formdata={
                                    'name': 'room.lightbox',
                                    'room_id': room_id,
                                    'hotel_id': listing['id'],
                                },
                                cb_kwargs={'listing': listing},
                                cookies=self.cookies,
                                headers=self.headers)
#FormRequest("https://www.booking.com/fragment.en-gb.json",formdata={'name': 'room.lightbox','room_id': room_id,'hotel_id': listing['id'],},cookies=cookies,headers=headers)

    def parse_room(self, response, listing):
        item = RoomItem()
        js = response.json()
        root = js['data']['rooms'][0]
        item['roomSizeInM2'] = float(root['b_surface_loc_value'])
        item['isNoSmoking'] = root['b_no_smoking']

        item['photos'] = []
        photo_item = PhotoItem()
        # response.json()['data']['rooms'][0]['b_room_data'][0]['b_photos']
        for photo in root['b_room_data'][0]['b_photos']:
            photo_item['url'] = 'https://cf.bstatic.com' + photo['b_uri_original']
            photo_item['id'] = photo['b_id']
            photo_item['width'] = photo['b_dimension_width_original']
            photo_item['height'] = photo['b_dimension_height_original']
            item['photos'].append(photo_item)

        item['facilities'] = []
        facility_item = RoomFacilityItem()
        for facility_id in (facilities := js['data']['data_from_spritzer']['room_facilities']['all_roomfacilities_by_facility_id']):
            facility_item['id'] = facility_id
            facility_item['name'] = facilities[facility_id]['name']
            facility_item['isHidden'] = bool(facilities[facility_id]['is_hidden'])
            facility_item['category'] = self.categories_list[facilities[facility_id]['roomfacility_type_id']]
            item['facilities'].append(facility_item)