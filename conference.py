#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'


from datetime import datetime, time
import json
import os
import time

import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import urlfetch
from google.appengine.ext import ndb
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import TeeShirtSize

from utils import getUserId

from settings import WEB_CLIENT_ID

from models import Conference
from models import ConferenceForm

from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms

from models import BooleanMessage
from models import ConflictException

from models import StringMessage

from models import Session
from models import SessionForm
from models import SessionForms
from models import SpeakerProperty
from models import SpeakerForm
from models import Speaker
from models import SessionType

from models import TeeShirtSizeForm


CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

SESSION_BYTYPE_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    typeOfSession=messages.StringField(2),
)

SESSION_BYSPEAKER_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeSpeakerKey=messages.StringField(1),
)

CONF_PUT_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

SESSION_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1),
)

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"],
}

OPERATORS = {
    'EQ':   '=',
    'GT':   '>',
    'GTEQ': '>=',
    'LT':   '<',
    'LTEQ': '<=',
    'NE':   '!='
}

FIELDS = {
    'CITY': 'city',
    'TOPIC': 'topics',
    'MONTH': 'month',
    'MAX_ATTENDEES': 'maxAttendees',
}

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID

MEMCACHE_ANNOUNCEMENTS_KEY = 'RECENT ANNOUNCEMENTS'
MEMCACHE_SPEAKERS_KEY = 'FEATURED SPEAKERS'

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference',
               version='v1',
               allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):

    """Conference API v0.1"""

# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(
                        pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))  # noqa
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""  # noqa
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # Get user id by calling getUserId(user)
        user_id = getUserId(user)

        # Create a new key of kind Profile from the id.
        p_key = ndb.Key(Profile, user_id)

        # Get the entity from datastore by using get() on the key
        profile = p_key.get()

        # If profile doesn't exist, we create a new one
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            # Save the profile to datastore
            profile.put()

        return profile      # return Profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
            # Put the modified profile to datastore
            prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm,
                      path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm,
                      path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)

# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create a Conference object, returning ConferenceForm/request."""  # noqa
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException(
                "Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound
        # Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on
        # start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(
                data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(
                data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        # both for data model & outbound Message
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # make Profile Key from user ID
        p_key = ndb.Key(Profile, user_id)
        # allocate new Conference ID with Profile key as parent
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        # make Conference key from ID
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference & return (modified) ConferenceForm
        Conference(**data).put()

        # Send confirmation email to the conference creator
        taskqueue.add(params={'email': user.email(),
                              'conferenceInfo': repr(request)},
                      url='/tasks/send_confirmation_email'
                      )

        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)  # noqa

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
                      http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_PUT_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(
                filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name)
                     for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is
                # performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences',
                      http_method='POST',
                      name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "")
                   for conf in conferences]
        )

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)  # noqa
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='getConferencesCreated',
                      http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # make profile key
        p_key = ndb.Key(Profile, getUserId(user))
        # create ancestor query for this user
        conferences = Conference.query(ancestor=p_key)
        # get the user profile and display name
        prof = p_key.get()

        displayName = getattr(prof, 'displayName')
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(
                conf, displayName) for conf in conferences]
        )

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='filterPlayground',
                      http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        q = Conference.query()

        # simple filter usage:
        # q = q.filter(Conference.city == "Paris")

        # advanced filter building and usage
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)

        q = q.filter(Conference.city == "London")
        q = q.filter(Conference.maxAttendees > 10)

        q = q.order(Conference.name)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )

# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='unregisterFromConference /{websafeConferenceKey}',
                      http_method='POST', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request, False)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        # step 1: get user profile
        prof = self._getProfileFromUser()

        # step 2: get conferenceKeysToAttend from profile.
        wscks = prof.conferenceKeysToAttend

        # step 3: fetch conferences from datastore.
        ds_keys = [ndb.Key(urlsafe=wsck) for wsck in wscks]

        conferences = ndb.get_multi(ds_keys)

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, "")
                                      for conf in conferences]
                               )

# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job.
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = '%s %s' % (
                'Last chance to attend! The following conferences '
                'are nearly sold out:',
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/announcement/get',
                      http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        announcement = memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY)
        if not announcement:
            announcement = ''
        return StringMessage(data=announcement)


# - - - Task 1: Session objects - - - - - - - - - - - - - - - - -

    def _getSpeaker(self, email):
        # Create a new key of kind Speaker from the id.
        s_key = ndb.Key(Speaker, email)

        # Get the entity from datastore by using get() on the key
        speaker = s_key.get()

        # If speaker doesn't exist, we create a new one
        if not speaker:
            speaker = Speaker(
                key=s_key,
                email=email,  # e-mail is enough, no name to store
            )
            # Save the speaker to datastore
            speaker.put()

        return speaker     # return Speaker

    def _addSessionToSpeaker(self, session_key, speakerForm):
        """Append session key to Speaker entity given in the parameter as SpeakerForm entity"""  # noqa
        speakerObj = self._getSpeaker(speakerForm.email)
        speakerObj.sessionKeysToAttend.append(session_key.urlsafe())
        speakerObj.put()
        # Return the speaker websafe key
        return speakerObj.key.urlsafe()

    def _copySessionToForm(self, sess):
        """Copy relevant fields from Session to SessionForm."""
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess, field.name):
                if field.name == 'speaker':
                    sf.speaker = SpeakerForm(
                        name=sess.speaker.name,
                        email=sess.speaker.email,
                        websafeSpeakerKey=sess.speaker.websafeSpeakerKey,
                    )

                # convert sessionType string to Enum
                elif field.name == 'sessionType':
                    setattr(
                        sf,
                        field.name,
                        getattr(SessionType, getattr(sess, field.name))
                    )
                # convert Date to date string
                elif field.name == 'date':
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                # just copy others
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
            # get the websafe session key
            elif field.name == 'websafeKey':
                setattr(sf, field.name, sess.key.urlsafe())
        sf.check_initialized()
        return sf

    def _createSessionObject(self, request):
        """Create a Session object, returning SessionForm/request."""
        # get the user
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # get Conference Key from websafeConferenceKey
        c_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        # get the actual Conference object
        conf = c_key.get()

        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)  # noqa

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Check that name was given
        if not request.name:
            raise endpoints.BadRequestException(
                "Session 'name' field required")

        # copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}

        # convert dates from ISO format strings to Date objects;
        # takes the first 10 characters of ISO format string.
        if data['date']:
            data['date'] = datetime.strptime(
                data['date'][:10], "%Y-%m-%d").date()

        if data['startTime']:
            # If start time was given we want to be sure it's in military
            # format
            startTimeDigits = len(str(data['startTime']))
            if startTimeDigits < 3 or startTimeDigits > 4:
                raise endpoints.BadRequestException(
                    "Start time must be in military notation (3 or 4 digits)")

        if data['sessionType']:
            # Convert enum field to string
            data['sessionType'] = data['sessionType'].name

        # allocate new Session ID with Conference key as parent
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        # make Session key from ID
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key

        # check whether the e-mail field is an empty string
        if not data['speaker'].email.strip():
            raise endpoints.BadRequestException(
                "Speaker 'e-mail' field cannot be empty"
            )

        # Add the websafe session key to the speaker object
        # and return the websafe speaker key
        wssk = self._addSessionToSpeaker(s_key, data['speaker'])
        speaker = SpeakerProperty(
            name=data['speaker'].name,
            email=data['speaker'].email,
            websafeSpeakerKey=wssk
        )

        # Overwrite the inbound SpeakerForm object with
        # the SpeakerProperty object
        data['speaker'] = speaker

        # Get rid of useless field. Session object has not such fields
        del data['websafeConferenceKey']
        del data['websafeKey']

        # create Session
        Session(**data).put()

        # Set a new featured speaker, if any
        taskqueue.add(
            params={'session': str(s_key.urlsafe())},
            url='/tasks/set_featured_speaker'
        )

        # return SessionForm object
        return self._copySessionToForm(s_key.get())

    @endpoints.method(CONF_GET_REQUEST, SessionForms,
                      path='getConferenceSessions/{websafeConferenceKey}',
                      http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Return all the sessions in a given conference."""
        # get Conference object from request; bail if not found
        wsck = request.websafeConferenceKey
        c_key = ndb.Key(urlsafe=wsck)
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # Get sessions for the given conference
        q = Session.query(ancestor=c_key).order(Session.name).fetch()

        # return set of SessionForm objects
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in q]
        )

    @endpoints.method(SESSION_POST_REQUEST, SessionForm,
                      path='createSession/{websafeConferenceKey}',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """Create a conference session."""
        return self._createSessionObject(request)

    @endpoints.method(SESSION_BYTYPE_GET_REQUEST, SessionForms,
                      path='getConferenceSessionsByType/{websafeConferenceKey}/{typeOfSession}',  # noqa
                      http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Return conference sessions by type."""
        # get Conference object from request; bail if not found
        wsck = request.websafeConferenceKey
        c_key = ndb.Key(urlsafe=wsck)
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # Turn the session type into an uppercased string
        sess_type = request.typeOfSession.upper()
        # Get sessions for the given conference, filtered by type
        q = Session.query(ancestor=c_key).\
            filter(Session.sessionType == sess_type).\
            order(Session.name).\
            fetch()

        # return set of SessionForm objects
        return SessionForms(
            items=[self._copySessionToForm(sess)for sess in q]
        )

    @endpoints.method(SESSION_BYSPEAKER_GET_REQUEST, SessionForms,
                      path='getSessionsBySpeaker/{websafeSpeakerKey}',
                      http_method='GET', name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """Get sessions by speaker, across al the conferences."""
        # get Speaker object from request; bail if not found
        wssk = request.websafeSpeakerKey
        speaker_key = ndb.Key(urlsafe=wssk)
        speaker = speaker_key.get()
        if not speaker:
            raise endpoints.NotFoundException(
                'No speaker found with key: %s' % wssk)

        # Get the sessions
        ds_keys = [ndb.Key(urlsafe=wssk) for wssk in speaker.sessionKeysToAttend]  # noqa
        q = ndb.get_multi(ds_keys)

        # return set of SessionForm objects
        return SessionForms(
            items=[self._copySessionToForm(sess)for sess in q]
        )


# - - - Task 2: Wishlist - - - - - - - - - - - - - - - - - - - -

    @endpoints.method(
        endpoints.ResourceContainer(
            message_types.VoidMessage,
            websafeSessionKey=messages.StringField(1),),
        ProfileForm,
        path='addSessionToWishlist/{websafeSessionKey}',
        http_method='POST',
        name='addSessionToWishlist'
    )
    def addSessionToWishlist(self, request):
        """Add a session to the user's wishlist"""
        # get Session object from request; bail if not found
        wssk = request.websafeSessionKey
        sess_key = ndb.Key(urlsafe=wssk)
        session = sess_key.get()
        print session
        if not session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % wssk)
        elif sess_key.kind() != 'Session':
            raise endpoints.BadRequestException(
                'The websafeKey: %s does not belong to a Session object' % wssk)  # noqa

        # Get the session's ancestor conference
        conference = sess_key.parent().get()

        # get user Profile
        prof = self._getProfileFromUser()

        # Check if user is registered to the conference
        if not conference.key.urlsafe() in prof.conferenceKeysToAttend:
            raise ConflictException(
                'You need to be registered to the conference in order to join a session')  # noqa

        # We don't want to have duplicates
        if wssk in prof.sessionKeysWishlist:
            raise ConflictException(
                'You have already added this session to your wishlist')

        # Add the session key to the user's wishlist
        prof.sessionKeysWishlist.append(wssk)
        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(
        message_types.VoidMessage,
        SessionForms,
        path='getSessionsInWishlist',
        http_method='GET',
        name='getSessionsInWishlist'
    )
    def getSessionsInWishlist(self, request):
        """Get all the sessions in the user's wishlist"""
        # get user Profile
        prof = self._getProfileFromUser()

        # Get the sessions
        ds_keys = [ndb.Key(urlsafe=wssk) for wssk in prof.sessionKeysWishlist]  # noqa
        q = ndb.get_multi(ds_keys)

        # return set of SessionForm objects
        return SessionForms(
            items=[self._copySessionToForm(sess)for sess in q]
        )

# - - - Task 3: Additional queries - - - - - - - - - - - - - - - - -

    @endpoints.method(
        endpoints.ResourceContainer(
            message_types.VoidMessage,
            date=messages.StringField(1),),
        SessionForms,
        path='getSessionsByDate',
        http_method='GET',
        name='getSessionsByDate'
    )
    def getSessionsByDate(self, request):
        """Get sessions on a given date (ISO format)."""
        date = None

        if request.date:
            try:
                date = datetime.strptime(
                    request.date[:10], "%Y-%m-%d").date()
            except ValueError:
                raise endpoints.BadRequestException(
                    "Session 'date' must be ISO format: YYYY-MM-DD")
        else:
            raise endpoints.BadRequestException(
                "Session 'date' field required")

        # convert dates from ISO format strings to Date objects;
        # takes the first 10 characters of ISO format string.
        q = Session.query(Session.date == date).\
            order(-Session.startTime)

        # return set of SessionForm objects
        return SessionForms(
            items=[self._copySessionToForm(sess)for sess in q]
        )

    @endpoints.method(
        CONF_GET_REQUEST,
        TeeShirtSizeForm,
        path='getTshirtsByConference',
        http_method='GET',
        name='getTshirtsByConference'
    )
    def getTshirtsByConference(self, request):
        """Get the amount of t-shirts, grouped by size, that are needed for the given conference"""  # noqa
        # get Conference object from request; bail if not found
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)  # noqa

        # Get all the people who are meant to attend the given conference
        q = Profile.query().filter(Profile.conferenceKeysToAttend == str(wsck))

        # Init a new TeeShirtSizeForm instance
        tShirts = TeeShirtSizeForm()

        # Loop through users attending the conference and add 1 unit
        # to the corresponging tshirt size group in the TeeShirtSizeForm
        # instance
        for user in q:
            setattr(
                tShirts,
                user.teeShirtSize,
                getattr(tShirts, user.teeShirtSize) + 1
            )

        # return TeeShirtSizeForm object
        return tShirts

    @endpoints.method(
        CONF_GET_REQUEST,
        SessionForms,
        path='getSessionsILike',
        http_method='GET',
        name='getSessionsILike'
    )
    def getSessionsILike(self, request):
        """Get all the sessions that starts before 7pm and
        that are not workshops, for a given conference"""
        # get Conference object from request; bail if not found
        wsck = request.websafeConferenceKey
        c_key = ndb.Key(urlsafe=wsck)
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # Get sessions which start before 7pm for the given conference
        q = Session.query(ancestor=c_key).\
            filter(Session.startTime < 1900).\
            order(Session.startTime).\
            fetch()

        # Init an empty list where to store filtered sessions
        filteredSessions = []

        # Filter out sessions which type is 'workshop';
        # we have to do it programmatically since datastore
        # doesn't support 2 inequality filters on the same query
        for sess in q:
            if sess.sessionType != 'WORKSHOP':
                filteredSessions.append(self._copySessionToForm(sess))

        # return set of SessionForm objects
        return SessionForms(
            items=filteredSessions
        )

# - - - Task 4: Featured Speaker - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheFeaturedSpeaker(websafeSessionKey):
        """Create Featured Speaker & assign to memcache; used by
        memcache cron job."""

        featuredSpeaker = {}

        # Get session
        new_s_key = ndb.Key(urlsafe=websafeSessionKey)
        new_session = new_s_key.get()
        if not new_session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % websafeSessionKey)

        # Retrieve conference parent's key
        c_key = new_s_key.parent()
        conference = c_key.get()

        # Get all the sessions for the given conference
        q = Session.query(ancestor=c_key).fetch()

        # Set an empty dictionary to hold the new session
        # speaker's websafe key and init it to 0
        new_speakerKey = {}
        new_speakerKey[new_session.speaker.websafeSpeakerKey] = 0

        # check if new speakers are attending more than one
        # session in the same conference
        for session in q:
            if session.speaker.websafeSpeakerKey in new_speakerKey:
                new_speakerKey[session.speaker.websafeSpeakerKey] += 1
                if new_speakerKey[session.speaker.websafeSpeakerKey] > 1:
                    featuredSpeaker['name'] = session.speaker.name
                    featuredSpeaker['email'] = session.speaker.email
                    break

        if any(featuredSpeaker):
            # If there is a featured speaker we put it in the memcache
            speaker = 'Come and listen to the best speakers! %s, %s, %s %s' % (
                featuredSpeaker['name'],
                featuredSpeaker['email'],
                'is going to attend the:',
                conference.name + ' conference!')
            memcache.set(MEMCACHE_SPEAKERS_KEY, speaker)

        return featuredSpeaker

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/getFeaturedSpeaker',
                      http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Get featured speakers."""
        speaker = memcache.get(MEMCACHE_SPEAKERS_KEY)
        if not speaker:
            speaker = 'There are no featured speakers'
        return StringMessage(data=speaker)

# registers API
api = endpoints.api_server([ConferenceApi])
