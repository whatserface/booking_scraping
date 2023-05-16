# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class ListingItem(scrapy.Item):
    id = scrapy.Field()
    name = scrapy.Field()
    seoDescription = scrapy.Field()
    address = scrapy.Field()
    coordinates = scrapy.Field()
    photos = scrapy.Field() # a list of PhotoItem instances
    check_in = scrapy.Field()
    check_out = scrapy.Field()

class RoomItem(scrapy.Item):
    id = scrapy.Field()
    name = scrapy.Field()
    roomSizeInM2 = scrapy.Field()
    rating = scrapy.Field()
    facilities = scrapy.Field()
    isNoSmoking = scrapy.Field()
    facilities = scrapy.Field() # a list of RoomFacilityItem instances

class RoomFacilityItem(scrapy.Item):
    id = scrapy.Field()
    name = scrapy.Field()
    isHidden = scrapy.Field()

class PhotoItem(scrapy.Item):
    id = scrapy.Field()
    url = scrapy.Field()
    width = scrapy.Field()
    height = scrapy.Field()
