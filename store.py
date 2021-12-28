import json
from json import JSONEncoder
from datetime import date, datetime

# subclass JSONEncoder
class DateTimeEncoder(JSONEncoder):
        #Override the default method
        def default(self, obj):
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()

class DataTools ():
    @staticmethod
    def check_integrity (data):
        for key in data:
            if key == 'supplies':
                if not isinstance (data[key], list):
                    return False
                else:
                    for i in data[key]:
                        if not all (k in i for k in ('cups', 'date_start', 'date_end', 'address', 'postal_code', 'province', 'municipality', 'distributor', 'pointType', 'distributorCode')):
                            return False
            elif key == 'contracts':
                if not isinstance (data[key], list):
                    return False
                else:
                    for i in data[key]:
                        if not all (k in i for k in ('date_start', 'date_end', 'marketer', 'distributorCode', 'power_p1', 'power_p2')):
                            return False
            elif key == 'consumptions':
                if not isinstance (data[key], list):
                    return False
                else:
                    for i in data[key]:
                        if not all (k in i for k in ('datetime', 'delta_h', 'value_kWh', 'real')):
                            return False
            elif key == 'maximeter':
                if not isinstance (data[key], list):
                    return False
                else:
                    for i in data[key]:
                        if not all (k in i for k in ('datetime', 'value_kW')):
                            return False
            elif key == 'pvpc':
                if not isinstance (data[key], list):
                    return False
                else:
                    for i in data[key]:
                        if not all (k in i for k in ('datetime', 'price')):
                            return False
        return True

    @staticmethod
    def datetime_parser(json_dict):
            for (key, value) in json_dict.items():
                if key in ['date_start', 'date_end', 'datetime']:
                    try:
                        json_dict[key] = datetime.fromisoformat(value)
                    except Exception:
                        pass
            return json_dict

async def async_load_storage (store):
    serialized_data = await store.async_load()
    old_data = json.loads(json.dumps(serialized_data), object_hook=DataTools.datetime_parser)
    if old_data is not None and old_data != {}:
        if DataTools.check_integrity(old_data):
            return old_data
    return False