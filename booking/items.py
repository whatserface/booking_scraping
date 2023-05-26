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
    distanceFromCentre = scrapy.Field()
    photos = scrapy.Field() # a list of PhotoItem instances
    spokenLanguages = scrapy.Field()
    check_in = scrapy.Field()
    check_out = scrapy.Field()
    hotelFacilities = scrapy.Field()
    rooms = scrapy.Field() # a list of RoomItem instances
    guestReviewsOverall = scrapy.Field()
    reviews = scrapy.Field() # a list of ReviewItem instances
    policies = scrapy.Field()
    hasReviews = scrapy.Field()

class RoomItem(scrapy.Item):
    id = scrapy.Field()
    name = scrapy.Field()
    photos = scrapy.Field()
    maxPersons = scrapy.Field()
    roomSizeInM2 = scrapy.Field()
    facilities = scrapy.Field()
    isNoSmoking = scrapy.Field()
    facilities = scrapy.Field() # a list of RoomFacilityItem instances
    beds = scrapy.Field()
    reviews = scrapy.Field()

class RoomFacilityItem(scrapy.Item):
    id = scrapy.Field()
    name = scrapy.Field()
    isHidden = scrapy.Field()
    category = scrapy.Field()

class ReviewItem(scrapy.Item):
    reviewer = scrapy.Field() # a ReviewerItem
    reviewDate = scrapy.Field()
    response = scrapy.Field()
    title = scrapy.Field()
    rating = scrapy.Field()
    liked = scrapy.Field()
    disliked = scrapy.Field()
    foundUseful = scrapy.Field()
    
class ReviewerItem(scrapy.Item):
    name = scrapy.Field()
    country = scrapy.Field()
    type = scrapy.Field()
    stayedInRoom = scrapy.Field() # { 'name': room_name, 'id': room_id }
    monthOfStay = scrapy.Field()
    numberOfNights = scrapy.Field()