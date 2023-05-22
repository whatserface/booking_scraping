import scrapy
from urllib.parse import urlencode
import json
import re
from scrapy import Request, FormRequest
from scrapy.http.response import Response

from booking.items import ListingItem, RoomItem, RoomFacilityItem


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
        for page in range(1, int(response.xpath('//li/button/text()').get())):
            self.params['offset'] = page * 25
            yield Request(self.basis + urlencode(self.params), callback=self.parse_page)
       
    def parse_page(self, response: Response):
        for url, distance_from_centre in zip(
                                    response.xpath('//h3/a/@href'),
                                    response.css('span[data-testid="distance"]::text')
                                ):
            yield response.follow(
                    url, callback=self.parse_listing, cb_kwargs={
                        'distance_from_centre': distance_from_centre
                    }
                )

    def parse_listing(self, response, distance_from_centre):
        listing = ListingItem()

        listing['distanceFromCentre'] = distance_from_centre

        js = json.loads(response.css("script[id$='SafetyDesktop'] + script::text").get())
        listing['name'] = js['HotelTranslation:{}']['name']
        listing['seoDescription'] = js['HotelTranslation:{}']['description']
        listing['languagesSpoken'] = js['PropertyPageFullExtendedAdamQueryResult:{}']['languagesSpoken']['languageCodes']
        listing['coordinates'] = js[js['PropertyPageFullExtendedAdamQueryResult:{}']['basicPropertyData']]['location']
        listing['coordinates'].pop('__typename', None)
        listing['coordinates'].pop('city', None)

        self.headers['x-booking-csrf'] = re.findall("'X-Booking-CSRF': '([^']+)'",
                response.xpath(
                    "//script[@class='jquery-script-tag']/preceding-sibling::script[position() = 2]/text()"
                ).get())[0]
        a = response.headers['Set-Cookie']
        self.cookies['bkng'] = a[(pos := a.find(b'bkng=')+5):a.find(b'; ', pos)]

        listing['id'] = response.xpath("//input[@name='hotel_id']/@value").get()

        listing['address'] = response.css("span.hp_address_subtitle::text").get().replace("\n", "")
        # in regex ".+(?:\n+.+)+" is an optimized version of "(.|\n)+"
        photos_file = re.findall("(?<=hotelPhotos: ).+(?:\n+.+)+(?=,\nb_hotelfeaturedreviews_url)", response.css("script[type='application/ld+json'] + script::text").get())[0]
        listing['photos']: list[str] = [i.replace("max1024x768", "max1280x900") for i in set(re.findall("large_url: '([^']+)'", photos_file))]

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

    def parse_room(self, response, listing):
        item = RoomItem()
        js = response.json()
        root = js['data']['rooms'][0]
        spritzer_data = js['data']['data_from_spritzer']
        item['name'] = root['b_name_gen']
        item['maxPersons'] = root['b_max_persons']
        item['roomSizeInM2'] = spritzer_data['surface_in_m2']
        item['isNoSmoking'] = root['b_no_smoking']

        item['photos'] = ['https://cf.bstatic.com' + photo['b_uri_original'].replace("max500", "max1280x900") for photo in root['b_room_data'][0]['b_photos']]

        facilities_by_ids: dict = spritzer_data['room_facilities']['categorized_room_facilities']['room_facilities_by_category']
        facility_item = RoomFacilityItem()
        facilities = spritzer_data['room_facilities']['all_roomfacilities_by_facility_id']
        for category in facilities_by_ids:
            item['facilities'][category] = []
            for facility_id in category['room_facility_ids']:
                facility_item['id'] = facility_id
                facility_item['name'] = facilities[facility_id]['name']
                facility_item['isHidden'] = bool(facilities[facility_id]['is_hidden'])
                facility_item['category'] = category
                item['facilities'][category].append(facility_item)

        item['policies'] = {k: v for k, v in root['b_terms_and_conditions'][0] if k.starstwith("b_general_policy")}
        if (quiet_hours := root['b_terms_and_conditions'][0].get('b_quiet_hours')):
            quiet_hours.pop('quiet_hours')
            item['policies']['quiet_hours'] = quiet_hours
        else:
            item['policies']['quiet_hours'] = None

        item['beds']: list[dict] = []
        beds = root['b_bed_type_configuration'] or root['b_room_data'][0]['b_apartment_room_config']
        for bed in beds:
            config = bed.get('configuration_type') or bed.get('b_apartment_bed_setup')
            item['beds'].append({config['b_room_type_translated']: {'name': config['name_withnumber'],
                                                                    '': config['']}})
            
        item['reviews'] = {}
        item['reviews']['comfy_beds'] = js['data']['b_comfy_beds']