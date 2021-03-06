#!/usr/bin/env python

"""models.py

Udacity conference server-side Python App Engine data & ProtoRPC models

$Id: models.py,v 1.1 2014/05/24 22:01:10 wesc Exp $

created/forked from conferences.py by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb


class BooleanMessage(messages.Message):  # needed for conference registrations

    """BooleanMessage-- outbound Boolean value message"""
    data = messages.BooleanField(1)


class ConflictException(endpoints.ServiceException):

    """ConflictException -- exception mapped to HTTP 409 response"""
    http_status = httplib.CONFLICT


# - - -Profile related classes - - - - - - - - - - - - - - - - - - -

class Profile(ndb.Model):

    """Profile -- User profile object"""
    displayName = ndb.StringProperty()
    mainEmail = ndb.StringProperty()
    teeShirtSize = ndb.StringProperty(default='NOT_SPECIFIED')
    conferenceKeysToAttend = ndb.StringProperty(repeated=True)
    sessionKeysWishlist = ndb.StringProperty(repeated=True)


class ProfileMiniForm(messages.Message):

    """ProfileMiniForm -- update Profile form message"""
    displayName = messages.StringField(1)
    teeShirtSize = messages.EnumField('TeeShirtSize', 2)


class ProfileForm(messages.Message):

    """ProfileForm -- Profile outbound form message"""
    userId = messages.StringField(1)
    displayName = messages.StringField(2)
    mainEmail = messages.StringField(3)
    teeShirtSize = messages.EnumField('TeeShirtSize', 4)
    conferenceKeysToAttend = messages.StringField(5, repeated=True)
    sessionKeysWishlist = messages.StringField(6, repeated=True)


# - - - TeeShirt related classes - - - - - - - - - - - - - - - - - - -

class TeeShirtSize(messages.Enum):

    """TeeShirtSize -- t-shirt size enumeration value"""
    NOT_SPECIFIED = 1
    XS_M = 2
    XS_W = 3
    S_M = 4
    S_W = 5
    M_M = 6
    M_W = 7
    L_M = 8
    L_W = 9
    XL_M = 10
    XL_W = 11
    XXL_M = 12
    XXL_W = 13
    XXXL_M = 14
    XXXL_W = 15


class TeeShirtSizeForm(messages.Message):

    """TeeShirtSizeForm -- outbound message which describes the
    amount of t-shirts, grouped by size, needed for each conference"""  # noqa
    NOT_SPECIFIED = messages.IntegerField(1, default=0)
    XS_M = messages.IntegerField(2, default=0)
    XS_W = messages.IntegerField(3, default=0)
    S_M = messages.IntegerField(4, default=0)
    S_W = messages.IntegerField(5, default=0)
    M_M = messages.IntegerField(6, default=0)
    M_W = messages.IntegerField(7, default=0)
    L_M = messages.IntegerField(8, default=0)
    L_W = messages.IntegerField(9, default=0)
    XL_M = messages.IntegerField(10, default=0)
    XL_W = messages.IntegerField(11, default=0)
    XXL_M = messages.IntegerField(12, default=0)
    XXL_W = messages.IntegerField(13, default=0)
    XXXL_M = messages.IntegerField(14, default=0)
    XXXL_W = messages.IntegerField(15, default=0)


# - - - Conference related classes - - - - - - - - - - - - - - - - - - -

class Conference(ndb.Model):

    """Conference -- Conference object"""
    name = ndb.StringProperty(required=True)
    description = ndb.StringProperty()
    organizerUserId = ndb.StringProperty()
    topics = ndb.StringProperty(repeated=True)
    city = ndb.StringProperty()
    startDate = ndb.DateProperty()
    month = ndb.IntegerProperty()
    endDate = ndb.DateProperty()
    maxAttendees = ndb.IntegerProperty()
    seatsAvailable = ndb.IntegerProperty()
    sessionKeys = ndb.StringProperty(repeated=True)


class ConferenceForm(messages.Message):

    """ConferenceForm -- Conference outbound form message"""
    name = messages.StringField(1)
    description = messages.StringField(2)
    organizerUserId = messages.StringField(3)
    topics = messages.StringField(4, repeated=True)
    city = messages.StringField(5)
    startDate = messages.StringField(6)
    month = messages.IntegerField(7)
    maxAttendees = messages.IntegerField(8)
    seatsAvailable = messages.IntegerField(9)
    endDate = messages.StringField(10)
    websafeKey = messages.StringField(11)
    organizerDisplayName = messages.StringField(12)


class ConferenceForms(messages.Message):

    """ConferenceForms -- multiple Conference outbound form message"""
    items = messages.MessageField(ConferenceForm, 1, repeated=True)


class ConferenceQueryForm(messages.Message):

    """ConferenceQueryForm -- Conference query inbound form message"""
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)


class ConferenceQueryForms(messages.Message):

    """ConferenceQueryForms -- multiple ConferenceQueryForm inbound form message"""  # noqa
    filters = messages.MessageField(ConferenceQueryForm, 1, repeated=True)


class StringMessage(messages.Message):

    """StringMessage-- outbound (single) string message"""
    data = messages.StringField(1, required=True)


# - - - Session related classes - - - - - - - - - - - - - - - - - - -

class SpeakerProperty(ndb.Model):

    """SpeakerProperty -- Speaker structured property for Session model"""
    email = ndb.StringProperty(required=True)
    name = ndb.StringProperty()
    websafeSpeakerKey = ndb.StringProperty()


class Session(ndb.Model):

    """Conference -- Conference object"""
    name = ndb.StringProperty(required=True)
    highlights = ndb.StringProperty()
    speaker = ndb.StructuredProperty(SpeakerProperty)
    date = ndb.DateProperty()
    duration = ndb.IntegerProperty()
    startTime = ndb.IntegerProperty()  # Military time notation
    sessionType = ndb.StringProperty()


class Speaker(ndb.Model):

    """Speaker -- Speaker object"""
    email = ndb.StringProperty(required=True)
    sessionKeysToAttend = ndb.StringProperty(repeated=True)


class SpeakerForm(messages.Message):

    """SpeakerForm -- Speaker outbound and inbound form message"""
    name = messages.StringField(1)
    email = messages.StringField(2, required=True)
    websafeSpeakerKey = messages.StringField(3)


class SessionForm(messages.Message):

    """SessionForm -- Session outbound and inbound form message"""
    name = messages.StringField(1)
    highlights = messages.StringField(2)
    speaker = messages.MessageField(SpeakerForm, 3)
    date = messages.StringField(4)
    duration = messages.IntegerField(5)
    startTime = messages.IntegerField(6)
    sessionType = messages.EnumField('SessionType', 7, default='NOT_SPECIFIED')
    websafeKey = messages.StringField(8)


class SessionForms(messages.Message):

    """SessionForms -- multiple Session outbound form message"""
    items = messages.MessageField(SessionForm, 1, repeated=True)


class SessionType(messages.Enum):

    """SessionType -- Session type value"""
    NOT_SPECIFIED = 1
    LECTURE = 2
    KEYNOTE = 3
    WORKSHOP = 4
