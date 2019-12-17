from datetime import datetime

## Method to remove empty values from a dictionary
def remove_empty_values_from_dict(dictionary):
	return {k: v for k, v in dictionary.items() if v is not None and v != '' and v != [] and v != {} }

def pretty_time(seconds):
    seconds = abs(int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days > 0:
        return '%dd %dh %dm %ds' % (days, hours, minutes, seconds)
    elif hours > 0:
        return '%dh %dm %ds' % (hours, minutes, seconds)
    elif minutes > 0:
        return '%dm %ds' % (minutes, seconds)
    else:
        return '%ds' % (seconds)

## Coverts a datetime to a specified string format.
def convert_datetime(dt, fmt):
    return dt.strftime(fmt)

## Formats RingCentral Call Metadata into a formatted note for a Close call
def format_ringcentral_call_note(note_data):
    keys = ["RC ID", "From", "To", "Duration", "Direction", "Result", "Reason", "Reason Description", "RC Users"]
    note = []
    note_key_data = {
		"RC ID": note_data.get('id'),
        "From": note_data['from']['phoneNumber'],
        "To": note_data['to']['phoneNumber'],
        "Duration": pretty_time(note_data['duration']),
        "Direction": note_data['direction'],
        'Result': note_data.get('result'),
        'Reason': note_data.get('reason'),
        'Reason Description': note_data.get('reasonDescription'),
		'RC Users': note_data.get('users')
    }
    note_key_data = remove_empty_values_from_dict(note_key_data)
    for key in keys:
        if key in note_key_data:
            note.append(f"{key}: {note_key_data[key]}" )
    if note:
        note = ['RingCentral Call:'] + note
        return '\n'.join(note)
    return None

## Formats RingCentral Call Data into a dictionary that can be POSTed to
## the Close API
def format_ringcentral_call_data(call_data):
	if call_data.get('duration') and call_data.get('result') == 'Missed':
		call_data['duration'] = 0
	close_call_data = {
        'lead_id': call_data['lead_id'],
        'duration': call_data.get('duration', 0),
        'direction': call_data.get('direction', 'outbound').lower(),
        'remote_phone': call_data.get('remote_phone'),
        'date_created': call_data.get('startTime', '').replace('Z', '+00:00'),
        'note': format_ringcentral_call_note(call_data)
    }
	return remove_empty_values_from_dict(close_call_data)
