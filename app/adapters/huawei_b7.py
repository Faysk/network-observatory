"""Original, read-only HG8247B7-8N/V5R024C00S114 adapter.

Schemas observed in the owner's GUI. Never execute returned JavaScript or log
raw responses. Authentication secrets exist only in the calling process memory.
"""
import base64
import http.client
import ipaddress
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from urllib.parse import urlencode

FIRMWARE = 'V5R024C00S114'
SOURCE = 'huawei-b7-http'
PATHS = {
    'optic': '/html/amp/opticinfo/newvdfopticinfo.asp',
    'wan': '/html/bbsp/wanStats/wanStatus_ptvdf.asp',
    'lan': '/html/bbsp/landhcp/landhcp_ptvdf.asp',
    'system': '/html/bbsp/status/Status_ptvdf.asp',
    'stations': '/html/amp/ptvdf/vdfClientMon.asp',
    'wan_states': '/html/bbsp/common/wan_list_cache_wan.asp',
    'wan_packets': '/html/bbsp/common/get_wan_list_ipwanstat.asp',
    'voice': '/html/voip/ptvdfvoipstatus/sipvoipmaintain.asp',
}
OPTIC = {'optical_tx_dbm': (1, -100, 100), 'optical_rx_dbm': (2, -100, 100),
         'optical_voltage_mv': (3, 0, 10000), 'optical_temp_c': (4, -100, 200),
         'optical_bias_ma': (5, 0, 1000), 'catv_rx_dbm': (6, -100, 100)}
COUNTERS = ('tx_packets', 'tx_bytes', 'tx_errors', 'tx_drops',
            'rx_packets', 'rx_bytes', 'rx_errors', 'rx_drops')
EXTRA_COUNTERS = ('tx_unicast_packets','rx_unicast_packets','tx_multicast_packets',
                  'rx_multicast_packets','tx_broadcast_packets','rx_broadcast_packets')
METRIC_LIMITS = {k:(v[1],v[2]) for k,v in OPTIC.items()}
METRIC_LIMITS.update(cpu_pct=(0,100), memory_pct=(0,100), uptime_seconds=(0,10**11))
CAPABILITIES = {10:'wmm',11:'power_save',12:'high_band',16:'80211k',17:'80211v',
                18:'dual_band',19:'beamforming',22:'twt_requester',23:'twt_responder',
                24:'bss_coloring',25:'ofdma',26:'mu_mimo',27:'80211w',28:'mimo',29:'80211r'}
LINK_STATES = {'Connected','Connecting','Disconnected','Disconnecting','Unconfigured',
               'PendingDisconnect','Authenticating','Error','Disabled','Up','Down'}
VOICE_STATES = {'Disabled','Up','Down','Registering','Registered','Unregistered','Error','Initializing','Quiescent'}
VOICE_ERRORS = {'ERROR_NONE','NONE','ERROR_TIMEOUT','ERROR_SERVER_UNREACHABLE',
                'ERROR_AUTHENTICATION','ERROR_AUTHENTICATION_FAILED','ERROR_SIP_REGISTRATION'}
SECTION_NAMES = {'system','wifi','stations','wan_states','wan_packets','voice','router_logs'}


class AdapterError(Exception):
    """Messages contain only fixed error codes, never response bodies."""


class AuthenticationError(AdapterError):
    pass


def load_credentials(path):
    """Read an explicitly selected local file; never echo its content."""
    from pathlib import Path
    try:
        with Path(path).open('r', encoding='utf-8-sig') as handle:
            text = handle.read(4097)
    except (OSError, UnicodeError):
        raise ValueError('Não foi possível ler o ficheiro de credenciais.') from None
    if len(text) > 4096:
        raise ValueError('Formato de credenciais inválido.')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    aliases = {'login':'username','user':'username','username':'username','utilizador':'username',
               'usuario':'username','usuário':'username','pass':'password','password':'password','senha':'password'}
    values = {}
    pending = None
    for line in lines:
        if pending:
            values[pending] = line
            pending = None
            continue
        parts = re.split(r'[:=]',line,maxsplit=1)
        key = aliases.get(parts[0].strip().lower())
        if key is None or key in values:
            raise ValueError('Formato de credenciais inválido; usa Login e Pass.')
        if len(parts) == 2 and parts[1].strip():
            values[key] = parts[1].strip()
        else:
            pending = key
    if pending or set(values) != {'username','password'}:
        raise ValueError('Credenciais incompletas; usa Login e Pass.')
    return values['username'], values['password']


def constructors(raw, name, count, allow_empty=False):
    if re.search(r'<input[^>]+(?:userpwd|type=[\"\x27]password)', raw, re.I):
        raise AuthenticationError('session_expired')
    result = []
    for match in re.finditer(r'new\s+' + re.escape(name) + r'\s*\(', raw):
        # The observed format uses quoted strings only. Reject expressions.
        token = r'"(?:[^"\\]|\\.)*"'
        arguments=re.match(r'(\s*'+token+r'(?:\s*,\s*'+token+r')*\s*)\)',raw[match.end():])
        if not arguments:
            raise AdapterError('unsupported_schema')
        args=arguments[1]
        try:
            values = json.loads('[' + re.sub(r'\\x([0-9a-fA-F]{2})', r'\\u00\1', args) + ']')
        except ValueError:
            raise AdapterError('unsupported_schema') from None
        if len(values) != count:
            raise AdapterError('unsupported_schema')
        result.append(values)
    if not result and not allow_empty:
        raise AdapterError('unsupported_schema')
    return result


def parse_model(raw):
    match = re.search(r'''var\s+productName\s*=\s*(["'])([A-Za-z0-9_\\-]+)\1''', raw)
    if not match:
        raise AdapterError('unsupported_model')
    model = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m[1],16)), match[2])
    if model not in ('HG8247B7','HG8247B7-8N'):
        raise AdapterError('unsupported_model')
    return model


def parse_identity(raw):
    rows=constructors(raw,'stDeviceInfo',3)
    if len(rows)!=1 or rows[0][1]!=FIRMWARE:
        raise AdapterError('unsupported_identity')
    return rows[0][1]


def integer(value, maximum=2**64-1):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,20}', value):
        raise AdapterError('invalid_counter')
    number = int(value)
    if number > maximum:
        raise AdapterError('invalid_counter')
    return number


def parse_optic(raw):
    rows = constructors(raw, 'stOpticInfo', 15)
    if len(rows) != 1:
        raise AdapterError('unsupported_schema')
    metrics = {}
    for key, (index, low, high) in OPTIC.items():
        text = rows[0][index].strip()
        if text in ('', '--', '-'):  # Missing is never converted to zero.
            continue
        if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', text):
            raise AdapterError('invalid_optic')
        value = float(text)
        if not math.isfinite(value) or not low <= value <= high:
            raise AdapterError('invalid_optic')
        metrics[key] = value
    if not metrics:
        raise AdapterError('missing_optic')
    # Vendor identifiers, serials, dates and unvalidated optical fields discarded.
    return metrics


def parse_wan(raw):
    result = {}
    for row in constructors(raw, 'WANStats', 9):
        match = re.fullmatch(r'InternetGatewayDevice\.WANDevice\.1\.WANConnectionDevice\.([1-9]\d*)\.WAN(?:IP|PPP)Connection\.1\.Stats', row[0])
        if not match:
            raise AdapterError('unsupported_schema')
        key = 'wan' + match[1]  # No unconfirmed Internet/VoIP/IPTV mapping.
        if key in result:
            raise AdapterError('duplicate_interface')
        result[key] = dict(zip(COUNTERS, map(integer, row[1:])))
    return result


def parse_lan(raw):
    result = {}
    for row in constructors(raw, 'LANStats', 13):
        match = re.fullmatch(r'InternetGatewayDevice\.X_HW_DEBUG\.AMP\.LANPort\.([1-4])\.Statistics', row[0])
        if not match:
            raise AdapterError('unsupported_schema')
        v = [integer(x, 2**32-1) for x in row[1:]]
        result['lan'+match[1]] = dict(zip(
            ('rx_bytes', 'rx_packets', 'rx_errors', 'rx_drops', 'tx_bytes', 'tx_packets', 'tx_errors', 'tx_drops'),
            (v[0]*2**32+v[1], v[2]*2**32+v[3], v[4], v[5],
             v[6]*2**32+v[7], v[8]*2**32+v[9], v[10], v[11])))
    for row in constructors(raw, 'ExtPortInfo', 4):
        match = re.fullmatch(r'InternetGatewayDevice\.LANDevice\.1\.LANEthernetInterfaceConfig\.([1-4])', row[0])
        if not match or 'lan'+match[1] not in result or row[1] not in ('Up', 'Down'):
            raise AdapterError('unsupported_schema')
        port = result['lan'+match[1]]
        port['link_up'] = row[1] == 'Up'
        mode = row[2].removeprefix('Auto_')
        speed = row[3].removeprefix('Auto_')
        port['duplex'] = mode.lower() if port['link_up'] and mode in ('Full', 'Half') else None
        port['speed_mbps'] = int(speed) if port['link_up'] and speed in ('10','100','1000','2500','10000') else None
    return result


def js_scalar(raw, name):
    match = re.search(r'''\bvar\s+''' + re.escape(name) + r'''\s*=\s*(["'])((?:\\.|[^\\])*?)\1''',raw)
    if not match:
        return None
    return re.sub(r'\\x([0-9a-fA-F]{2})',lambda m:chr(int(m[1],16)),match[2]).strip()


def reported_number(value, low, high, integral=False):
    value=value.strip()
    if value in ('','--','-'):
        return None
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',value):
        raise AdapterError('invalid_reported_number')
    number=float(value)
    if not math.isfinite(number) or not low <= number <= high or (integral and not number.is_integer()):
        raise AdapterError('invalid_reported_number')
    return int(number) if integral else number


def flag(value):
    return {'0':False,'1':True}.get(value.strip())


def wlan_key(domain):
    match=re.fullmatch(r'InternetGatewayDevice\.LANDevice\.1\.WLANConfiguration\.(\d+)(?:\.(?:Stats|AssociatedDevice\.\d+))?',domain)
    if not match or not 1 <= int(match[1]) <= 16:
        raise AdapterError('unsupported_wlan_domain')
    return 'wlan'+match[1]


def parse_system(raw):
    metrics={}
    for var,key in (('cpuUsed','cpu_pct'),('memUsed','memory_pct')):
        value=js_scalar(raw,var)
        if value is not None:
            number=reported_number(value.removesuffix('%'),0,100)
            if number is not None:metrics[key]=number
    rows=constructors(raw,'stDeviceInfo',6)
    if len(rows)!=1 or rows[0][3]!=FIRMWARE:
        raise AdapterError('unsupported_system_identity')
    uptime=reported_number(rows[0][5],0,10**11,True)
    if uptime is not None:metrics['uptime_seconds']=uptime
    system={}
    if re.fullmatch(r'[A-Za-z0-9_.-]{1,32}',rows[0][2]):system['hardware_version']=rows[0][2]
    dhcp=constructors(raw,'stMainDhcpInfo',3,allow_empty=True)
    if dhcp:system['dhcp_enabled']=flag(dhcp[0][1])
    wifi={}
    for row in constructors(raw,'stWlan',8):
        channel=reported_number(row[5],0,233,True)
        wifi[wlan_key(row[0])]={'enabled':flag(row[1]),'channel':channel,
                              'link_up':{'Up':True,'Down':False}.get(row[7])}
    return metrics,system,wifi


def parse_wifi_counters(raw):
    result={}
    for row in constructors(raw,'stPacketInfo',5,allow_empty=True):
        key=wlan_key(row[0])
        result[key]=dict(zip(('tx_bytes','tx_packets','rx_bytes','rx_packets'),map(integer,row[1:])))
    for row in constructors(raw,'stStats',5,allow_empty=True):
        key=wlan_key(row[0])
        result.setdefault(key,{}).update(zip(('tx_errors','rx_errors','tx_drops','rx_drops'),map(integer,row[1:])))
    return result


def parse_stations(raw):
    if not re.search(r'function\s+stAssociatedDevice\s*\(',raw):
        raise AdapterError('unsupported_station_schema')
    wifi={}
    for row in constructors(raw,'stWlan',24):
        key=wlan_key(row[0])
        channel=reported_number(row[13],0,233,True)
        values={'enabled':flag(row[1]),'channel':channel,
                'band':('2.4GHz' if channel and channel<=14 else '5GHz' if channel else None),
                'transmit_power_pct':reported_number(row[18],0,100),
                'client_limit':reported_number(row[22],0,4096,True),
                'bandwidth_code':reported_number(row[17],0,100,True),
                'service_enabled':flag(row[19]),'hidden':flag(row[20]),
                'wmm_enabled':flag(row[21]),'auto_channel':flag(row[23])}
        if re.fullmatch(r'[A-Za-z0-9_+/,.-]{1,40}',row[15]):values['standard_reported']=row[15]
        wifi[key]=values
    stations=[]
    numeric={2:('uptime_seconds',0,10**11),3:('rx_link_mbps',0,100000),
             4:('tx_link_mbps',0,100000),5:('rssi_dbm',-200,0),6:('noise_dbm_reported',-200,0),
             7:('snr_db_reported',0,200),8:('signal_quality_reported',0,100)}
    for row in constructors(raw,'stAssociatedDevice',30,allow_empty=True):
        observation={'interface':wlan_key(row[0])}
        mac=normalise_mac(row[1])
        if mac:observation['mac']=mac
        address=client_ip(row[13])
        if address:observation['ip']=address
        if clean_label(row[14]):observation['description']=clean_label(row[14])
        for index,(key,low,high) in numeric.items():
            number=reported_number(row[index],low,high)
            if number is not None:observation[key]=number
        observation['capabilities']={name:flag(row[index]) for index,name in CAPABILITIES.items()}
        if re.fullmatch(r'[A-Za-z0-9_+/,.-]{1,40}',row[9]):observation['working_mode_reported']=row[9]
        if re.fullmatch(r'[1-8]\*[1-8]',row[15]):observation['antenna_configuration']=row[15].replace('*','x')
        stations.append(observation)
    if len(stations)>128:raise AdapterError('too_many_stations')
    inventory={'online_rows':0,'offline_rows':0,'other_rows':0}
    for row in constructors(raw,'USERDeviceInfo',10,allow_empty=True):
        key={'Online':'online_rows','Offline':'offline_rows'}.get(row[4],'other_rows')
        inventory[key]+=1
    return wifi,stations,inventory


def normalise_mac(value):
    if not isinstance(value,str):return None
    value=value.replace('-',':').lower()
    if re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',value) and value not in ('00:00:00:00:00:00','ff:ff:ff:ff:ff:ff'):
        return value
    return None


def client_ip(value):
    try:
        address=ipaddress.ip_address(value)
        if address.is_unspecified or address.is_multicast or address.is_loopback:return None
        return str(address)
    except ValueError:return None


def clean_label(value):
    """Bounded device metadata, never executable HTML or constructor arguments."""
    return ''.join(c for c in value if c.isprintable()).strip()[:128]


def parse_clients(raw, stations, lan_raw=''):
    """Join confirmed GUI inventory rows to Wi-Fi observations by MAC only."""
    clients={}
    def get(mac):
        return clients.setdefault(mac,{'mac':mac,'names':[],'ips':[],'ports':[],
                                      'device_types':[],'reported_status':'Unknown'})
    def add(values,value):
        if value and value not in values and len(values)<16:values.append(value)
    for row in constructors(raw,'USERDeviceInfo',10,allow_empty=True):
        mac=normalise_mac(row[1])
        if not mac:continue
        device=get(mac)
        for index in (6,8):add(device['names'],clean_label(row[index]))
        for index in (3,7):add(device['device_types'],clean_label(row[index]))
        port=clean_label(row[5])+':'+clean_label(row[2])
        add(device['ports'],port[:128])
        status=row[4] if row[4] in ('Online','Offline') else 'Unknown'
        if device['reported_status']!='Online':device['reported_status']=status
        lease=reported_number(row[9],0,2**32-1,True) if re.fullmatch(r'\d{1,10}',row[9]) else None
        if lease is not None:device['lease_remaining_seconds']=max(device.get('lease_remaining_seconds',0),lease)
    for station in stations:
        if 'mac' not in station:continue
        device=get(station['mac'])
        device['reported_status']='Online'
        add(device['ips'],station.get('ip'))
        add(device['names'],station.get('description'))
        add(device['ports'],station['interface'])
    for row in constructors(lan_raw,'NeighInfo',5,allow_empty=True):
        # This table also contains ISP/WAN next hops. Only LAN-scoped rows are clients.
        interface=row[3].lower()
        if not (interface.startswith('internetgatewaydevice.landevice.1.') or re.fullmatch(r'(?:lan[1-4]|wlan\d+)',interface)):
            continue
        mac=normalise_mac(row[2]);address=client_ip(row[1])
        if not mac or not address:continue
        device=get(mac)
        add(device['ips'],address)
        add(device['ports'],clean_label(row[3]))
        state=row[4].lower()
        if state in ('reachable','stale','delay','probe','incomplete','failed','permanent','unknown'):
            add(device.setdefault('neighbor_states',[]),state)
    if len(clients)>1024:raise AdapterError('too_many_clients')
    return list(clients.values())


def is_lan_client(client):
    """Hide historic WAN-neighbour-only rows from the household inventory."""
    return bool(client.get('names')) or any(re.match(r'(?:eth:|wifi:|wlan\d|lan[1-4]|internetgatewaydevice\.landevice\.1\.)',p.lower()) for p in client.get('ports',[]))


def parse_health(raw):
    row=constructors(raw,'stOpticInfo',15)[0]
    result={}
    for index,key in ((11,'tx_wavelength_reported'),(12,'rx_wavelength_reported'),(13,'max_distance_reported'),(14,'los_status_code')):
        value=reported_number(row[index],0,100000)
        if value is not None:result[key]=value
    mode=js_scalar(raw,'ontPonMode')
    if mode in ('gpon','epon','10g-gpon','ge'):result['pon_mode']=mode
    match=re.search(r'function\s+GetLinkState\s*\(\)\s*\{\s*var\s+State\s*=\s*([01])\s*;',raw)
    if match:result['pon_connected']=match[1]=='1'
    return result


def parse_wan_states(raw):
    result={}
    for row in constructors(raw,'WanIP',63):
        match=re.fullmatch(r'InternetGatewayDevice\.WANDevice\.1\.WANConnectionDevice\.(\d+)\.WANIPConnection\.1',row[0])
        if not match:raise AdapterError('unsupported_wan_domain')
        values={'enabled':flag(row[9]),'nat_enabled':flag(row[18]),
                'ipv4_enabled':flag(row[30]),'ipv6_enabled':flag(row[31])}
        if row[12] in LINK_STATES:values['connection_state']=row[12]
        services=[]
        for token in re.split(r'[, _]+',row[26].upper()):
            name={'INTERNET':'Internet','VOIP':'VoIP','IPTV':'IPTV','TR069':'Management'}.get(token)
            if name and name not in services:services.append(name)
        values['services']=services
        uptime=reported_number(row[43],0,10**11,True)
        if uptime is not None:values['uptime_seconds']=uptime
        result['wan'+match[1]]=values
    return result


def parse_wan_packets(raw):
    result={}
    for row in constructors(raw,'WaninfoStats',11):
        match=re.fullmatch(r'InternetGatewayDevice\.WANDevice\.1\.WANConnectionDevice\.(\d+)\.WANIPConnection\.1(?:\.Stats)?',row[0])
        if not match:raise AdapterError('unsupported_wan_domain')
        result['wan'+match[1]]=dict(zip(EXTRA_COUNTERS,map(integer,row[5:11])))
    return result


def parse_wan_packet_totals(raw):
    result=parse_wan_packets(raw)
    for row in constructors(raw,'WaninfoStats',11):
        match=re.search(r'WANConnectionDevice\.(\d+)\.',row[0])
        result['wan'+match[1]].update(zip(('tx_bytes','rx_bytes','tx_packets','rx_packets'),map(integer,row[1:5])))
    return result


def parse_voice(raw):
    result={}
    for row in constructors(raw,'stLine',6):
        match=re.fullmatch(r'InternetGatewayDevice\.Services\.VoiceService\.\d+\.VoiceProfile\.\d+\.Line\.(\d+)',row[0])
        if not match or not 1<=int(match[1])<=16:raise AdapterError('unsupported_voice_domain')
        values={}
        if row[3] in VOICE_STATES:values['registration_state']=row[3]
        if row[5] in VOICE_ERRORS:values['registration_error']=row[5]
        result['line'+match[1]]=values
    return result


def validate_payload(data, require_recent=True):
    """Strict allowlist at the local ingestion boundary."""
    required={'collected_at', 'metrics', 'interfaces', 'firmware'}
    if not isinstance(data, dict) or not required <= set(data) or set(data)-required-{'system','wifi','stations','clients','wan_states','wan_packet_totals','inventory','voice','health','sections','observability'}:
        raise ValueError('Invalid telemetry payload')
    if data['firmware'] != FIRMWARE:
        raise ValueError('Unsupported firmware')
    try:
        stamp = datetime.fromisoformat(data['collected_at'])
        age = (datetime.now(timezone.utc)-stamp).total_seconds()
    except (ValueError, TypeError):
        raise ValueError('Invalid collection time') from None
    if age < -5 or (require_recent and age > 180):
        raise ValueError('Collection time is stale or in the future')
    metrics, interfaces = data['metrics'], data['interfaces']
    if not isinstance(metrics, dict) or not metrics or set(metrics)-set(METRIC_LIMITS):
        raise ValueError('Invalid optical fields')
    for key, value in metrics.items():
        if type(value) not in (float, int) or not math.isfinite(value) or not METRIC_LIMITS[key][0] <= value <= METRIC_LIMITS[key][1]:
            raise ValueError('Invalid optical metric')
    if not isinstance(interfaces, dict) or not 1 <= len(interfaces) <= 20:
        raise ValueError('Invalid interfaces')
    for key, values in interfaces.items():
        if not re.fullmatch(r'(?:lan[1-4]|wan[1-9]\d?)', key) or not isinstance(values, dict):
            raise ValueError('Invalid interface')
        expected = set(COUNTERS) | ({'link_up','duplex','speed_mbps'} if key.startswith('lan') else set())
        if not expected <= set(values) or set(values)-expected-(set(EXTRA_COUNTERS) if key.startswith('wan') else set()):
            raise ValueError('Invalid interface fields')
        for field in set(values) & (set(COUNTERS)|set(EXTRA_COUNTERS)):
            if type(values[field]) is not int or not 0 <= values[field] <= 2**64-1:
                raise ValueError('Invalid counter')
        if key.startswith('lan') and (type(values['link_up']) is not bool or values['duplex'] not in (None,'full','half') or values['speed_mbps'] not in (None,10,100,1000,2500,10000)):
            raise ValueError('Invalid link')
    validate_extensions(data)
    if 'observability' in data:
        from app.router_observability import validate
        validate(data['observability'])
    return data


def validate_extensions(data):
    """Allow authorised client identity; reject secrets and unknown fields."""
    def numeric(v,lo,hi):
        return v is None or (type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi)
    boolean=lambda v:v is None or type(v) is bool
    count=lambda v:numeric(v,0,2**64-1)
    enum=lambda *items:lambda v:v in items
    schema={
      'system':{'hardware_version':lambda v:isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,32}',v)), 'dhcp_enabled':boolean},
      'wifi':{**{k:count for k in COUNTERS},**{k:boolean for k in ('enabled','link_up','service_enabled','hidden','wmm_enabled','auto_channel')},
              'channel':lambda v:numeric(v,0,233),'band':enum(None,'2.4GHz','5GHz'),
              'transmit_power_pct':lambda v:numeric(v,0,100),'client_limit':lambda v:numeric(v,0,4096),
              'bandwidth_code':lambda v:numeric(v,0,100),'standard_reported':lambda v:isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z0-9_+/,.-]{1,40}',v))},
      'wan_states':{**{k:boolean for k in ('enabled','nat_enabled','ipv4_enabled','ipv6_enabled')},'connection_state':enum(*LINK_STATES),
                    'uptime_seconds':lambda v:numeric(v,0,10**11),'services':lambda v:isinstance(v,list) and len(v)<=4 and all(x in ('Internet','VoIP','IPTV','Management') for x in v)},
      'wan_packet_totals':{k:lambda v:type(v) is int and 0<=v<=2**64-1 for k in ('tx_bytes','rx_bytes','tx_packets','rx_packets')+EXTRA_COUNTERS},
      'inventory':{k:count for k in ('online_rows','offline_rows','other_rows')},
      'voice':{'registration_state':enum(*VOICE_STATES),'registration_error':enum(*VOICE_ERRORS)},
      'health':{**{k:lambda v:numeric(v,0,100000) for k in ('tx_wavelength_reported','rx_wavelength_reported','max_distance_reported','los_status_code')},'pon_mode':enum('gpon','epon','10g-gpon','ge'),'pon_connected':boolean},
      'sections':{k:enum('ok','unavailable','not_collected') for k in SECTION_NAMES}}
    def check(obj, rules):
        if not isinstance(obj,dict) or set(obj)-set(rules):raise ValueError('Invalid extension fields')
        for k,v in obj.items():
            if not rules[k](v):raise ValueError('Invalid extension value')
    for section,rules in schema.items():
        if section not in data:continue
        obj=data[section]
        if section in ('wifi','wan_states','wan_packet_totals','voice'):
            pattern={'wifi':r'wlan(?:[1-9]|1[0-6])','wan_states':r'wan[1-9]\d?','wan_packet_totals':r'wan[1-9]\d?','voice':r'line(?:[1-9]|1[0-6])'}[section]
            if not isinstance(obj,dict) or len(obj)>32:raise ValueError('Invalid extension map')
            for k,v in obj.items():
                if not re.fullmatch(pattern,k):raise ValueError('Invalid extension key')
                check(v,rules)
        else:check(obj,rules)
    stations=data.get('stations',[])
    if not isinstance(stations,list) or len(stations)>128:raise ValueError('Invalid stations')
    rules={'interface':lambda v:isinstance(v,str) and bool(re.fullmatch(r'wlan(?:[1-9]|1[0-6])',v)),
           'mac':lambda v:normalise_mac(v)==v and v is not None,
           'ip':lambda v:isinstance(v,str) and client_ip(v)==v,
           'description':lambda v:isinstance(v,str) and len(v)<=128 and clean_label(v)==v,
           'uptime_seconds':lambda v:numeric(v,0,10**11),
           **{k:lambda v:numeric(v,0,100000) for k in ('rx_link_mbps','tx_link_mbps')},
           **{k:lambda v:numeric(v,-200,0) for k in ('rssi_dbm','noise_dbm_reported')},
           'snr_db_reported':lambda v:numeric(v,0,200),'signal_quality_reported':lambda v:numeric(v,0,100),
           'working_mode_reported':lambda v:isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z0-9_+/,.-]{1,40}',v)),
           'antenna_configuration':lambda v:isinstance(v,str) and bool(re.fullmatch(r'[1-8]x[1-8]',v)),
           'capabilities':lambda v:isinstance(v,dict) and not set(v)-set(CAPABILITIES.values()) and all(boolean(x) for x in v.values())}
    for station in stations:check(station,rules)
    clients=data.get('clients',[])
    if not isinstance(clients,list) or len(clients)>1024:raise ValueError('Invalid clients')
    labels=lambda v:isinstance(v,list) and len(v)<=16 and all(isinstance(x,str) and 0<len(x)<=128 and clean_label(x)==x for x in v)
    rules={'mac':lambda v:normalise_mac(v)==v and v is not None,
           **{k:labels for k in ('names','ports','device_types','neighbor_states')},
           'ips':lambda v:isinstance(v,list) and len(v)<=16 and all(isinstance(x,str) and client_ip(x)==x for x in v),
           'reported_status':enum('Online','Offline','Unknown'),
           'lease_remaining_seconds':lambda v:type(v) is int and 0<=v<=2**32-1}
    seen=set()
    for client in clients:
        check(client,rules)
        if not {'mac','reported_status'}<=set(client) or client['mac'] in seen:raise ValueError('Invalid client identity')
        seen.add(client['mac'])


class HuaweiB7:
    def __init__(self, host, username, password, interval=60, clock=time.monotonic):
        ip = ipaddress.ip_address(host)
        if ip.version != 4 or not any(ip in ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
            raise ValueError('Private IPv4 required')
        self.host, self.username, self.password = str(ip), username, password
        self.interval, self.clock = max(60, interval), clock
        self.cookie = None
        self.verified_model = None
        self.connection = None
        self.last_login_attempt = float('-inf')
        self.renewals = 0
        self.next_attempt = 0
        self.failures = 0
        self.cached = None
        self.observation_cache = None
        self.next_observation_attempt = 0
        self.authentication_error = AuthenticationError
        self.lock = threading.Lock()

    def _request(self, connection, method, path, body=None, cookie=None):
        from app.router_observability import SOURCES
        allowed = set(PATHS.values()) | {v[0] for v in SOURCES.values()} | {'/', '/index.asp', '/asp/GetRandCount.asp', '/login.cgi'}
        if path not in allowed or (method != 'GET' and (method != 'POST' or path not in ('/asp/GetRandCount.asp','/login.cgi'))):
            raise AdapterError('request_not_allowed')
        headers = {'Referer': 'http://'+self.host+'/', 'Content-Type':'application/x-www-form-urlencoded'}
        if cookie:
            headers['Cookie'] = cookie
        for attempt in range(2):
            try:
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                break
            except (OSError, http.client.HTTPException):
                # An idle keep-alive socket can have been closed by the router.
                # Retry a confirmed GET once, never replay a login POST.
                if method != 'GET' or attempt:
                    raise
                connection.close()
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise AdapterError('response_too_large')
        if response.status in (401,403):
            raise AuthenticationError('session_expired')
        if response.status not in (200,301,302,303):
            raise AdapterError('router_http_error')
        if response.status != 200 and path != '/login.cgi':
            raise AuthenticationError('session_expired')
        return raw.decode('utf-8-sig',errors='replace'), response.getheaders()

    def _login(self, conn):
        now = self.clock()
        if now-self.last_login_attempt < 60:
            raise AuthenticationError('login_rate_limited')
        self.last_login_attempt = now
        token, _ = self._request(conn,'POST','/asp/GetRandCount.asp', b'')
        token = token.strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,256}', token):
            raise AuthenticationError('invalid_login_challenge')
        body = urlencode({'UserName':self.username, 'PassWord':base64.b64encode(self.password.encode()).decode(),
                          'Language':'portuguese','x.X_HW_Token':token})
        _, headers = self._request(conn,'POST','/login.cgi', body, 'Cookie=body:Language:portuguese:id=-1')
        jar = SimpleCookie()
        for name, value in headers:
            if name.lower() == 'set-cookie':
                jar.load(value)
        if not jar:
            raise AuthenticationError('login_failed')
        self.cookie = '; '.join(f'{name}={item.value}' for name,item in jar.items())

    def collect(self):
        with self.lock:
            now = self.clock()
            if now < self.next_attempt:
                if self.cached is not None and not self.failures:
                    return self.cached
                raise AdapterError('backoff_active')
            self.next_attempt = now+self.interval
            if self.connection is None:
                self.connection = http.client.HTTPConnection(self.host,80,timeout=8)
            conn = self.connection
            successful = False
            try:
                if self.verified_model is None:
                    landing, _ = self._request(conn,'GET','/')
                    self.verified_model = parse_model(landing)
                if not self.cookie:
                    self._login(conn)
                try:
                    payload = self._read_data(conn)
                except AuthenticationError:
                    # Only renew a previously proven session, once per cycle.
                    if self.cached is None:
                        raise
                    self.cookie = None
                    # The router's 403 leaves the old transport unusable even
                    # when its response advertises Keep-Alive. Start a fresh
                    # connection before obtaining a new login challenge.
                    conn.close()
                    self._login(conn)
                    self.renewals += 1
                    payload = self._read_data(conn)
                validate_payload(payload)
                self.cached = payload
                self.failures = 0
                successful = True
                return payload
            except AuthenticationError:
                self.cookie = None
                self._failed(now)
                raise
            except (OSError, http.client.HTTPException):
                self._failed(now)
                raise AdapterError('router_unreachable') from None
            except AdapterError:
                self._failed(now)
                raise
            except ValueError:
                self._failed(now)
                raise AdapterError('unsupported_response') from None
            finally:
                if not successful:
                    self.close()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _read_data(self, conn):
        identity, _ = self._request(conn,'GET','/index.asp',cookie=self.cookie)
        parse_identity(identity)
        optic, _ = self._request(conn,'GET',PATHS['optic'],cookie=self.cookie)
        wan, _ = self._request(conn,'GET',PATHS['wan'],cookie=self.cookie)
        lan, _ = self._request(conn,'GET',PATHS['lan'],cookie=self.cookie)
        payload={'collected_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'firmware':FIRMWARE, 'metrics':parse_optic(optic),
                'interfaces':{**parse_wan(wan), **parse_lan(lan)}}
        payload.update(wifi=parse_wifi_counters(lan),health=parse_health(optic),sections={'router_logs':'not_collected'})
        for section,parser in (('system',parse_system),('stations',parse_stations),('wan_states',parse_wan_states),('wan_packets',parse_wan_packet_totals),('voice',parse_voice)):
            try:
                raw,_=self._request(conn,'GET',PATHS[section],cookie=self.cookie)
                parsed=parser(raw)
                if section=='system':
                    metrics,system,wifi=parsed
                    payload['metrics'].update(metrics);payload['system']=system
                    for key,value in wifi.items():payload['wifi'].setdefault(key,{}).update(value)
                elif section=='stations':
                    wifi,stations,inventory=parsed
                    payload.update(stations=stations,inventory=inventory,clients=parse_clients(raw,stations,lan))
                    for key,value in wifi.items():payload['wifi'].setdefault(key,{}).update(value)
                elif section=='wan_packets':
                    payload['wan_packet_totals']=parsed
                    for key,value in parsed.items():
                        if key in payload['interfaces']:payload['interfaces'][key].update({k:v for k,v in value.items() if k in EXTRA_COUNTERS})
                else:payload[section]=parsed
                payload['sections'][section]='ok'
            except AuthenticationError:
                raise
            except (AdapterError,OSError,http.client.HTTPException):
                payload['sections'][section]='unavailable'
                conn.close()
        payload['sections']['wifi']='ok' if payload['wifi'] else 'unavailable'
        from app.router_observability import collect
        payload['observability']=collect(self,conn)
        return payload

    def _failed(self, now):
        self.failures += 1
        self.next_attempt = now + (900 if self.failures >= 3 else self.interval * 2**self.failures)


def main():
    import argparse
    import getpass
    import os
    parser = argparse.ArgumentParser(description='Coletor Huawei B7 somente leitura; credenciais apenas em memória')
    parser.add_argument('--host', default=os.environ.get('FNO_ROUTER_IP','192.168.1.1'))
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--with-probes', action='store_true', help='Executa também as sondas já configuradas para gateway e destino externo')
    parser.add_argument('--audit-cycles',type=int,default=0,help='Verifica 1–10 recolhas contra respostas em memória e SQLite, sem guardar páginas brutas')
    parser.add_argument('--credentials-file', help='Ficheiro local autorizado; conteúdo nunca é mostrado')
    parser.add_argument('--serve', action='store_true', help='Inicia dashboard neste processo, sem sondas de dispositivos')
    parser.add_argument('--bind', default=os.environ.get('FNO_BIND', '127.0.0.1'), help='Endereço de escuta do dashboard; padrão loopback')
    parser.add_argument('--port',type=int,default=int(os.environ.get('FNO_PORT','8765')))
    args = parser.parse_args()
    if not 0<=args.audit_cycles<=10 or (args.audit_cycles and not args.serve):
        parser.error('--audit-cycles requer --serve e um número entre 1 e 10')
    token = os.environ.get('FNO_INGEST_TOKEN','')
    if args.serve and not token:
        import secrets
        token = secrets.token_urlsafe(32)
    if len(token) < 32:
        raise SystemExit('Define FNO_INGEST_TOKEN com pelo menos 32 caracteres, igual ao servidor.')
    if args.credentials_file:
        try:
            username, password = load_credentials(args.credentials_file)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
    else:
        username = input('Utilizador do router: ').strip()
        password = getpass.getpass('Password do router (não é guardada): ')
    if not username or not password:
        raise SystemExit('Credenciais obrigatórias; nenhuma tentativa efetuada.')
    adapter = HuaweiB7(args.host,username,password)
    if args.audit_cycles:
        from app.audit import LiveAudit
        adapter.audit=LiveAudit(adapter,args.audit_cycles)
    if args.serve:
        from http.server import ThreadingHTTPServer
        from app import core
        from app.server import Handler, READ_ALLOWED_CIDRS
        if args.bind not in ('127.0.0.1','localhost','::1') and not READ_ALLOWED_CIDRS:
            print('Leitura LAN bloqueada por padrão: configure FNO_READ_ALLOW_CIDRS para os clientes autorizados.')
        core.WRITE_TOKEN = token
        core.init_db()
        try:
            server = ThreadingHTTPServer((args.bind,args.port),Handler)
        except OSError:
            raise SystemExit('Porta local ocupada. Usa --port 8767 ou outra porta livre.') from None
        from app import host_telemetry
        host_telemetry.start(core.DB_PATH, args.port)
        worker = threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        probe_stop=threading.Event()
        probe_worker=None
        if args.with_probes:
            probe_worker=threading.Thread(target=core.collector_loop,args=(probe_stop,),daemon=True)
            probe_worker.start()
        print(f'Dashboard: http://{args.bind}:{args.port} · token temporário apenas em memória')
        try:
            run_collector(adapter,args.port,token,args.watch,keep_serving_on_auth_error=True)
        finally:
            adapter.close()
            probe_stop.set()
            if probe_worker:probe_worker.join(8)
            server.shutdown()
            server.server_close()
            worker.join(3)
        return
    try:
        run_collector(adapter,args.port,token,args.watch)
    finally:
        adapter.close()


def run_collector(adapter, port, token, watch, keep_serving_on_auth_error=False):
    from urllib.request import Request, build_opener, ProxyHandler
    opener = build_opener(ProxyHandler({}))
    from app.outbox import Outbox
    from app import core
    outbox=Outbox(core.DB_PATH.parent/'outbox')
    def deliver(result):
        stamp=datetime.fromisoformat(result['collected_at'])
        historical=(datetime.now(timezone.utc)-stamp).total_seconds()>180
        headers={'Content-Type':'application/json','X-API-Key':token}
        if historical:headers['X-FNO-Backfill']='1'
        request=Request(f'http://127.0.0.1:{port}/api/ingest/huawei',data=json.dumps(result,allow_nan=False).encode(),headers=headers)
        with opener.open(request,timeout=8) as response:
            if response.status!=201:raise AdapterError('local_ingest_failed')
    while True:
        try:
            core.set_collector_state('collecting',last_attempt=core.utcnow(),reason=None)
            # Recover acknowledged-or-pending samples before reading new device data.
            try:
                outbox.flush(deliver)
                if outbox.last_quarantined:
                    print('Fila: amostras inválidas isoladas sem eliminação:',outbox.last_quarantined)
            except Exception:print('Envio anterior pendente na fila local; nova recolha será preservada.')
            collection_started = time.perf_counter()
            result = adapter.collect()
            from app import host_telemetry
            host_telemetry.record_collection((time.perf_counter()-collection_started)*1000)
            outbox.enqueue(result)
            outbox.flush(deliver)
            if outbox.last_quarantined:
                print('Fila: amostras inválidas isoladas sem eliminação:',outbox.last_quarantined)
            core.set_collector_state('ok',last_success=result['collected_at'],reason=None)
            audit=getattr(adapter,'audit',None)
            if audit:
                try:audit.finish(result,port)
                except Exception:
                    print('Auditoria indisponível; amostra já guardada. Consultar testes e relatório local.')
            print('Recolha guardada:',result['collected_at'],len(result['interfaces']),'interfaces · renovações:',adapter.renewals)
        except AuthenticationError:
            core.set_collector_state('auth_blocked',reason='authentication_failed')
            if keep_serving_on_auth_error and watch:
                adapter.close()
                print('Autenticação bloqueada; painel e histórico continuam disponíveis. Reinício manual necessário após verificar o acesso.')
                while True:time.sleep(1)
            raise SystemExit('Autenticação falhou/expirou. Coletor parado; não repete credenciais automaticamente.') from None
        except Exception as exc:
            code = str(exc) if isinstance(exc,AdapterError) else 'local_ingest_unavailable'
            core.set_collector_state('backoff',reason='collection_unavailable')
            print('Recolha indisponível:',code,'· sem atualização das métricas.')
            if not watch:
                raise SystemExit(1) from None
        if not watch:
            return
        time.sleep(max(60,adapter.next_attempt-adapter.clock()))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
