import logging
import scrapy
from urllib.parse import urlencode
import json
import re
from scrapy import Request, FormRequest
from scrapy.http.response import Response

from booking.items import ListingItem, RoomItem, RoomFacilityItem, ReviewItem, ReviewerItem


class ListingsScrapeSpider(scrapy.Spider):
    name = "listings_scrape"
    allowed_domains = ["www.booking.com"]
    # during the execution of program this variable changes, see self.parse_reviews.

    base = "https://www.booking.com/searchresults.en-gb.html?"
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
    start_urls = [base + urlencode(params)]

    def __init__(self, name=None, **kwargs):
        super().__init__(name, **kwargs)
        self.headers = {}
        self.cookies = {}

        # for reviews iterations
        self.last_page = 0
        self.curr_page = 0

    def parse(self, response):
        # pagination crawl
        yield from self.parse_page(response)
        # for page in range(1, int(response.xpath('//li/button/text()').get())):
        #     self.params['offset'] = page * 25
        #     yield Request(self.basis + urlencode(self.params), callback=self.parse_page)
       
    def parse_page(self, response: Response):
        # i = 0
        for url, distance_from_centre in zip(
                                    response.xpath('//h3/a/@href'),
                                    response.css('span[data-testid="distance"]::text').getall()
                                ):
            # i += 1
            # if i == 2:
            #     break
            yield response.follow(
                    url, callback=self.parse_listing, cb_kwargs={
                        'distance_from_centre': distance_from_centre
                    }
                )

    def parse_listing(self, response, distance_from_centre):
        listing = ListingItem()

        listing['distanceFromCentre'] = distance_from_centre

        js = json.loads(response.xpath("//script[contains(text(), 'ROOT_QUERY')]/text()").get())
        listing['name'] = js['HotelTranslation:{}']['name']
        listing['seoDescription'] = js['HotelTranslation:{}']['description']
        listing['spokenLanguages'] = js['PropertyPageFullExtendedAdamQueryResult:{}']['languagesSpoken']['languageCodes']
        listing['coordinates'] = js[js['PropertyPageFullExtendedAdamQueryResult:{}']['basicPropertyData']['__ref']]['location']
        listing['coordinates'].pop('__typename', None)
        listing['coordinates'].pop('city', None)

        listing['hotelFacilities'] = [v['instances'][0]['title'] for k, v in js.items() if 'BaseFacility' in k]

        listing['hasReviews'] = 'review' in response.css('a[aria-controls="hp-reviews-sliding"]::text').get()
        
        guest_reviews_overall = [v for k, v in js['ROOT_QUERY'].items() if 'reviewsFrontend' in k][0]['ratingScores'] if listing['hasReviews']\
                                    else []
        listing['guestReviewsOverall'] = []
        for generalized_review in guest_reviews_overall:
            listing['guestReviewsOverall'].append({'name': generalized_review['name'],
                                                   'value': generalized_review['value']})

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
        
        listing['check_in'] = self.get_check(response, 'in')
        listing['check_out'] = self.get_check(response, 'out')

        
        listing['rooms'] = []

        # parsing rooms and reviews

        if listing['hasReviews']:
            url = response.url

            pagename = url[url.find('hotel/cz/')+9:url.find('.', 20)]

        rooms_ids = response.xpath(
                "//div[@class='room-lightbox-container js-async-room-lightbox-container']/@data-room-id"
            ).getall()
        for i, room_id in enumerate(rooms_ids):
            yield FormRequest("https://www.booking.com/fragment.en-gb.json", self.parse_room,
                                    formdata={
                                    'name': 'room.lightbox',
                                    'room_id': room_id,
                                    'hotel_id': listing['id'],
                                },
                                cb_kwargs={'listing': listing, 'is_last': i == (len(rooms_ids) - 1), 'pagename': pagename},
                                cookies=self.cookies,
                                headers=self.headers)
        

    def parse_room(self, response, listing, is_last, pagename):
        item = RoomItem()
        js = response.json()

        root = js['data']['rooms'][0]
        spritzer_data = js['data']['data_from_spritzer']

        if type(js) == 'dict':
            with open('debug.json', 'w') as f:
                json.dump(js, f, ensure_ascii=False)

        item['id'] = js['data']['b_room_id']
        item['name'] = root['b_name_gen']
        logging.info(f'Parsing room {item["name"]} with id {item["id"]}')
        item['maxPersons'] = root['b_max_persons']
        item['roomSizeInM2'] = root['b_room_data'][0]['b_surface_in_m2']
        item['isNoSmoking'] = root['b_room_data'][0]['b_no_smoking']

        item['photos'] = ['https://cf.bstatic.com' + photo['b_uri_original'].replace("max500", "max1280x900") for photo in root['b_room_data'][0]['b_photos']]

        logging.debug(f'D {spritzer_data}')
        facilities_categorized: dict = spritzer_data['room_facilities']['categorized_room_facilities']['room_facilities_by_category']
        facilities_by_ids = spritzer_data['room_facilities']['all_roomfacilities_by_facility_id']
        item['facilities'] = {}
        for category in facilities_categorized:
            item['facilities'][category] = []
            for facility_id in facilities_categorized[category]['room_facility_ids']:
                if not facilities_by_ids.get(str(facility_id)):
                    continue
                facility_item = RoomFacilityItem()
                facility_item['id'] = facility_id
                facility_id = str(facility_id)
                facility_item['name'] = facilities_by_ids[facility_id]['name']
                facility_item['isHidden'] = bool(facilities_by_ids[facility_id]['is_hidden'])
                facility_item['category'] = category
                item['facilities'][category].append(facility_item)

        if not listing.get('policies'):
            listing['policies'] = {k: v for k, v in root['b_terms_and_conditions'][0].items() if k.startswith("b_general_policy")}
            if (quiet_hours := root['b_terms_and_conditions'][0].get('b_quiet_hours')):
                quiet_hours.pop('quiet_hours')
                listing['policies']['quiet_hours'] = quiet_hours
            else:
                listing['policies']['quiet_hours'] = None

        

        item['beds']: list[dict] = []
        beds = root['b_bed_type_configuration'] or root['b_apartment_room_config']
        for bed in beds:
            configs = bed.get('bed_type') or bed.get('b_apartment_bed_setup')
            for config in configs:
                item['beds'].append({(config.get('b_room_type_translated') or config.get('name')): 
                                    {
                                        'name': config['name_withnumber'],
                                        'sizeDescription': config['description'],
                                        'maxPersons': config.get('max_persons') or config['occupancy']
                                    }
                                })
            
        item['reviews'] = js['data'].get('b_comfy_beds')
        listing['rooms'].append(item)
        
        if is_last and listing['hasReviews']:
            self.params = {
                'cc1': 'cz',
                'pagename': pagename,
                'offset': 0,
                'rows': 10,
            }
            listing['reviews'] = []
            yield response.follow('https://www.booking.com/reviewlist.en-gb.html?' + urlencode(self.params),
                    callback=self.parse_reviews, cookies=self.cookies, headers=self.headers,
                    cb_kwargs={'listing': listing}
                )
        else:
            yield listing if is_last else None
    
    def parse_reviews(self, response, listing):
        reviews = response.xpath('//div[@class="c-review-block"]/div[@class="bui-grid"]')
        logging.info(f"Parsing the {self.curr_page + 1}/{self.last_page} page of reviews")
        if not self.last_page:
            self.last_page = int(response.xpath('//a[@class="bui-pagination__link"]/@data-page-number')[-1].get())
        
        with open('debug.html', 'w') as f:
            f.write(response.text)

        should_check_for_each_foundUseful = bool(reviews.xpath('.//p/strong'))
        for review in reviews:
            item = ReviewItem()
            reviewer = ReviewerItem()
            item['title'] = review.xpath('.//h3/text()').get()
            item['rating'] = float(review.xpath('.//div[@class="bui-review-score__badge"]/text()').get())
            item['foundUseful'] = review.xpath('.//p/strong/text()').get() if should_check_for_each_foundUseful else None
            if item['foundUseful']:
                item['foundUseful'] = int(re.search(r'\d+', item['foundUseful']).group())
            item['liked'] = review.css('span.c-review__prefix--color-green + span + span::text').get()
            item['disliked'] = review.css('span.c-review__prefix:not(.c-review__prefix--color-green) + span + span::text').get()
            reviewer['monthOfStay'], item['reviewDate'] = [i.replace('\n', '').replace('Reviewed: ', '') for i in review.css('span.c-review-block__date::text').getall()]
            
            reviewer['name'] = review.css('span.bui-avatar-block__title::text').get()
            reviewer['country'] = review.css('span.bui-avatar-block__subtitle::text').get()
            room_name = review.css('a div::text').get()
            if room_name:
                room_name = room_name.replace('\n', '')
            else:
                room_name = None
            nights = review.xpath('.//li/div[contains(text(), "night")]/text()').get()
            reviewer['type'] = review.css('ul.review-panel-wide__traveller_type div::text').get()
            reviewer['numberOfNights'] = int(re.search(r'\d+', nights).group())
            reviewer['monthOfStay'] = review.css('li div span::text').get()
            reviewer['stayedInRoom'] = {'name': room_name, 'room_id': review.xpath('.//li/@data-room-id').get()}

            item['response'] = (review.css('span.c-review-block__response__body.bui-u-hidden::text') or 
                                review.css('span.c-review-block__response__body:not(.bui-u-hidden)::text'))
            item['response'] = item['response'].get()
            item['reviewer'] = reviewer
            listing['reviews'].append(item)

        if self.curr_page < self.last_page - 1:
            self.curr_page += 1
            self.params['offset'] = self.curr_page * self.params['rows']
            yield scrapy.Request('https://www.booking.com/reviewlist.en-gb.html?' + urlencode(self.params),
                                cookies=self.cookies, headers=self.headers, cb_kwargs={'listing': listing},
                                callback=self.parse_reviews                  
                            )
        else:
            yield listing
        
    
    # helper functions
    def get_check(self, response: Response, type):
        check = response.xpath(f'//div[@id="check{type}_policy"]/p[text() != "\n"]/text()').getall()
        if len(check) == 0:
            return [None, None]
        check = check[0]
        check_from = re.findall('(?<=from )\d{2}:\d{2}', check, re.IGNORECASE) or None
        check_to = re.findall('(?<=to  )\d{2}:\d{2}', check, re.IGNORECASE) or None
        return [check_from and check_from[0], check_to and check_to[0]]