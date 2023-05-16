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
    photos = scrapy.Field()

class RoomItem(scrapy.Item):
    id = scrapy.Field()
    name = scrapy.Field()
    room_size = scrapy.Field()
    rating = scrapy.Field()
    facilities = scrapy.Field()
    isNoSmoking = scrapy.Field()
    facilities = scrapy.Field() # a list of RoomFacilityItems

class RoomFacilityItem(scrapy.Item):
    id = scrapy.Field()
