from closeio_api import Client as CloseIO_API, APIError
import os
from ringcentral import SDK
from urllib.parse import urlencode
from datetime import datetime, timedelta
from .format_rc_to_close import convert_datetime, format_ringcentral_call_data
import logging
import json
import time


## Initiate Logger
log_format = "[%(asctime)s] %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)

## Initiate Close API
api = CloseIO_API(os.environ.get('CLOSE_API_KEY'))
org_id = api.get('api_key/' + os.environ.get('CLOSE_API_KEY'))['organization_id']
dev_api = CloseIO_API(os.environ.get('CLOSE_DEV_API_KEY'))

##############################################
# Close Methods
##############################################

## Method to get most recent completed sync time from the Master Lead in the Development Sandbox
## If we cannot get the most recent completed sync time, we default to 5 minutes before the
## current time
def get_sync_time_from_close(current_time):
    if os.environ.get('MASTER_LEAD_ID'):
        try:
            lead = dev_api.get('lead/' + os.environ.get('MASTER_LEAD_ID'), params={ '_fields': 'custom' })
            if lead['custom'].get('last_ringcentral_sync_time'):
                return datetime.strptime(lead['custom']['last_ringcentral_sync_time'].split('+')[0].split('.')[0], '%Y-%m-%dT%H:%M:%S')
        except APIError as e:
            logging.error("No Master Lead could be found...")
    return (current_time - timedelta(seconds=300))

## Method to set the sync time on the Master Lead in Close once a RingCentral sync has been completed at a particular time.
def set_sync_time_in_close(last_ringcentral_sync_time):
    if os.environ.get('MASTER_LEAD_ID'):
        try:
            dev_api.put('lead/' + os.environ.get('MASTER_LEAD_ID'), data={ 'custom.last_ringcentral_sync_time': last_ringcentral_sync_time })
        except APIError as e:
            logging.error("Could not update sync time on lead because we could not get the master lead...")


## Method to find Close leads that have a specific phone number on them, so we know which leads to log
## RingCentral calls on.
def find_close_lead_ids_from_phone_number(phone_number):
    lead_ids = []
    try:
        has_more = True
        offset = 0
        while has_more:
            resp = api.get('lead', params={ '_skip': offset, 'query': f'phone_number:"{phone_number}"', '_fields': 'id' })
            lead_ids += [i['id'] for i in resp['data']]
            offset += len(resp['data'])
            has_more = resp['has_more']
        if not lead_ids:
            # Create lead if it does not exist
            lead = api.post('lead', data={'contacts': [{ 'phones': [{ 'phone': phone_number, 'type': 'office'}]}]})
            lead_ids.append(lead['id'])
        return lead_ids
    except APIError as e:
        logging.error(f"Failed to find Close leads that matched the phone number {phone_number} because {str(e)}...")
        return None

## Method to log a call on a Close lead given the Close call data
def log_close_call(call_data):
    try:
        api.post('activity/call', data=call_data)
    except APIError as e:
        logging.error(f"Failed to log a call on Close lead {call_data['lead_id']} because {str(e)}...")

## Method to check if call is already on lead by RingCentral ID
def call_on_lead(lead_id, rc_id, date_created):
    try:
        resp = api.get('activity/call', params={ 'lead_id': lead_id, 'date_created__gte': date_created, '_fields': 'id,note' })
        for call in resp['data']:
            if call.get('note') and rc_id in call['note']:
                logging.info(f"Call was on lead")
                return True
    except:
        logging.error(f"Could not check if {rc_id} was on lead {lead_id}")
    return False
##############################################
# RingCentral Methods
##############################################

## Initialize RingCentral API.
platform = SDK(
    os.environ.get('RINGCENTRAL_CLIENT_ID'),
    os.environ.get('RINGCENTRAL_CLIENT_SECRET'),
    os.environ.get('RINGCENTRAL_SERVER')
).platform()
platform.login(
    os.environ.get('RINGCENTRAL_USERNAME'),
    "",
    os.environ.get('RINGCENTRAL_PASSWORD')
)

## Method to Refresh rc platform for new tokens every hour because they expire
def refresh_rc_platform():
    platform.refresh()
    logging.info("Token for RC was refreshed...")

## Method to GET all RingCentral Calls in a specified time range from the RingCentral Call Log API and return them in an array
def get_ringcentral_calls(date_from, date_to):
    calls = []
    has_more = True
    page = 1
    query = {
        'type': 'Voice',
        'dateFrom': date_from,
        'dateTo': date_to,
        'view': 'Detailed'
    }
    try:
        while has_more:
            query['page'] = page
            resp = platform.get('/restapi/v1.0/account/~/call-log/?' + urlencode(query)).json_dict()
            calls += [i for i in resp['records']]
            page += 1
            has_more = bool(resp['navigation'].get('nextPage'))
            ## Protect ourselves from ratelimits
            if has_more:
                time.sleep(6)
    except Exception as e:
        logging.error(f"Failed to get calls because {str(e)}")
    return calls

## Method to find RC Users names from Detailed Legs
def find_rc_users(legs):
    users = []
    for leg in legs:
        if leg.get('legType') == 'Accept':
            if leg.get('from') and leg['from'].get('extensionId') and leg['from'].get('name'):
                users.append(leg['from']['name'])
            if leg.get('to') and leg['to'].get('extensionId') and leg['to'].get('name'):
                users.append(leg['to']['name'])
    if users:
        return ', '.join(users)
    return []

## Method to process a call and log it in Close
def process_call(rc_call):
    if rc_call.get('id') and rc_call.get('startTime'):
        if rc_call.get('to') and rc_call.get('from') and 'phoneNumber' in rc_call['from'] and 'phoneNumber' in rc_call['to']:
            phone = rc_call['to']['phoneNumber'] if rc_call.get('direction') == 'Outbound' else rc_call['from']['phoneNumber']
            if phone:
                close_ids = find_close_lead_ids_from_phone_number(phone)
                for lead_id in close_ids:
                    rc_call['lead_id'] = lead_id
                    rc_call['remote_phone'] = phone
                    if rc_call.get('legs'):
                        rc_call['users'] = find_rc_users(rc_call['legs'])
                    on_lead = call_on_lead(lead_id, rc_call['id'], rc_call['startTime'].split('T')[0])
                    if not on_lead:
                        formatted_call_data = format_ringcentral_call_data(rc_call)
                        if formatted_call_data:
                            log_close_call(formatted_call_data)

## Start a time ranged GET of RingCentral Data and add any found calls into Close. This is a job that runs on APScheduler.
def find_and_post_rc_calls_to_close():
    current_time = datetime.utcnow()
    last_ringcentral_sync_time = get_sync_time_from_close(current_time)
    formatted_last_sync_time = convert_datetime(last_ringcentral_sync_time, '%Y-%m-%dT%H:%M:%SZ')
    formatted_current_time = convert_datetime(current_time, '%Y-%m-%dT%H:%M:%SZ')
    rc_calls = get_ringcentral_calls(formatted_last_sync_time, formatted_current_time)
    for call in rc_calls:
        process_call(call)
    set_sync_time_in_close(convert_datetime(current_time, '%Y-%m-%dT%H:%M:%S+00:00'))
    logging.info(f"Ran sync between {convert_datetime(last_ringcentral_sync_time, '%x %I:%M:%S %p')} UTC - {convert_datetime(current_time, '%x %I:%M:%S %p')} UTC")
