"""Independent read-reference and lossless-storage audit. Raw pages never leave RAM."""
import json
import math
import re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

MISSING=object()

def leaves(value,path=''):
    if isinstance(value,dict):
        if not value:yield path,value
        for key,item in value.items():yield from leaves(item,f'{path}.{key}' if path else key)
    elif isinstance(value,list):
        if not value:yield path,value
        for index,item in enumerate(value):yield from leaves(item,f'{path}[{index}]')
    else:yield path,value

def differences(expected,actual,path=''):
    if type(expected) is not type(actual):return [path or '$']
    if isinstance(expected,dict):
        result=[(path+'.'+k).strip('.') for k in set(expected)^set(actual)]
        for key in expected.keys()&actual.keys():result.extend(differences(expected[key],actual[key],(path+'.'+key).strip('.')))
        return result
    if isinstance(expected,list):
        result=[path+'.length'] if len(expected)!=len(actual) else []
        for index,(left,right) in enumerate(zip(expected,actual)):result.extend(differences(left,right,f'{path}[{index}]'))
        return result
    return [] if expected==actual else [path]

def rows(raw,name,count):
    """Reference reader for string literals; never executes device JavaScript."""
    result=[]
    for marker in re.finditer(r'\bnew\s+'+re.escape(name)+r'\s*\(',raw):
        rest=raw[marker.end():];args=[]
        while True:
            rest=rest.lstrip()
            token=re.match(r'"(?:[^"\\]|\\.)*"',rest)
            if not token:raise ValueError('reference_schema')
            args.append(json.loads(re.sub(r'\\x([0-9A-Fa-f]{2})',r'\\u00\1',token[0])))
            rest=rest[len(token[0]):].lstrip()
            if rest.startswith(')'):break
            if not rest.startswith(','):raise ValueError('reference_schema')
            rest=rest[1:]
        if len(args)!=count:raise ValueError('reference_arity')
        result.append(args)
    return result

def scalar(raw,name):
    match=re.search(r'\bvar\s+'+re.escape(name)+r'''\s*=\s*(["'])(.*?)\1''',raw)
    return re.sub(r'\\x([0-9A-Fa-f]{2})',lambda m:chr(int(m[1],16)),match[2]).strip() if match else None

def num(value,integer=False):
    if value.strip() in ('','--','-'):return None
    return int(value) if integer else float(value)

def bit(value):return {'0':False,'1':True}.get(value.strip())
def wlan(domain):return 'wlan'+re.search(r'WLANConfiguration\.(\d+)',domain)[1]
def wan(domain):return 'wan'+re.search(r'WANConnectionDevice\.(\d+)',domain)[1]
def label(value):return ''.join(c for c in value if c.isprintable()).strip()[:128]
def mac(value):
    value=value.lower().replace('-',':')
    return value if re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',value) and value not in ('00:00:00:00:00:00','ff:ff:ff:ff:ff:ff') else None

def reference_payload(pages,statuses):
    """Mappings verified from this firmware's GUI constructor parameter names."""
    from ipaddress import ip_address
    def ip(value):
        try:
            address=ip_address(value)
            return str(address) if not(address.is_unspecified or address.is_multicast or address.is_loopback) else None
        except ValueError:return None
    result={'firmware':rows(pages['index'],'stDeviceInfo',3)[0][1],'metrics':{},'interfaces':{},'wifi':{},'health':{},'sections':statuses}
    metrics=result['metrics'];interfaces=result['interfaces'];wifi=result['wifi'];health=result['health']
    optical=rows(pages['optic'],'stOpticInfo',15)[0]
    for index,key in enumerate(('optical_tx_dbm','optical_rx_dbm','optical_voltage_mv','optical_temp_c','optical_bias_ma','catv_rx_dbm'),1):
        value=num(optical[index])
        if value is not None:metrics[key]=value
    for index,key in ((11,'tx_wavelength_reported'),(12,'rx_wavelength_reported'),(13,'max_distance_reported'),(14,'los_status_code')):
        value=num(optical[index])
        if value is not None:health[key]=value
    mode=scalar(pages['optic'],'ontPonMode')
    if mode in ('gpon','epon','10g-gpon','ge'):health['pon_mode']=mode
    link=re.search(r'function\s+GetLinkState\s*\(\)\s*\{\s*var\s+State\s*=\s*([01])\s*;',pages['optic'])
    if link:health['pon_connected']=link[1]=='1'
    for row in rows(pages['wan'],'WANStats',9):
        interfaces[wan(row[0])]={key:int(row[i]) for i,key in enumerate(('tx_packets','tx_bytes','tx_errors','tx_drops','rx_packets','rx_bytes','rx_errors','rx_drops'),1)}
    for row in rows(pages['lan'],'LANStats',13):
        key='lan'+re.search(r'LANPort\.(\d+)',row[0])[1]
        interfaces[key]={'rx_bytes':int(row[1])*4294967296+int(row[2]),'rx_packets':int(row[3])*4294967296+int(row[4]),'rx_errors':int(row[5]),'rx_drops':int(row[6]),'tx_bytes':int(row[7])*4294967296+int(row[8]),'tx_packets':int(row[9])*4294967296+int(row[10]),'tx_errors':int(row[11]),'tx_drops':int(row[12])}
    for row in rows(pages['lan'],'ExtPortInfo',4):
        key='lan'+re.search(r'LANEthernetInterfaceConfig\.(\d+)',row[0])[1];up=row[1]=='Up';duplex=row[2].removeprefix('Auto_');speed=row[3].removeprefix('Auto_')
        interfaces[key].update(link_up=up,duplex=duplex.lower() if up and duplex in ('Full','Half') else None,speed_mbps=int(speed) if up and speed in ('10','100','1000','2500','10000') else None)
    for row in rows(pages['lan'],'stPacketInfo',5):wifi[wlan(row[0])]={key:int(row[i]) for i,key in enumerate(('tx_bytes','tx_packets','rx_bytes','rx_packets'),1)}
    for row in rows(pages['lan'],'stStats',5):wifi.setdefault(wlan(row[0]),{}).update({key:int(row[i]) for i,key in enumerate(('tx_errors','rx_errors','tx_drops','rx_drops'),1)})
    if statuses.get('system')=='ok':
        raw=pages['system'];device=rows(raw,'stDeviceInfo',6)[0];system={};result['system']=system
        for variable,key in (('cpuUsed','cpu_pct'),('memUsed','memory_pct')):
            value=scalar(raw,variable)
            if value is not None:
                value=num(value.removesuffix('%'))
                if value is not None:metrics[key]=value
        value=num(device[5],True)
        if value is not None:metrics['uptime_seconds']=value
        if re.fullmatch(r'[A-Za-z0-9_.-]{1,32}',device[2]):system['hardware_version']=device[2]
        dhcp=rows(raw,'stMainDhcpInfo',3)
        if dhcp:system['dhcp_enabled']=bit(dhcp[0][1])
        for row in rows(raw,'stWlan',8):wifi.setdefault(wlan(row[0]),{}).update(enabled=bit(row[1]),channel=num(row[5],True),link_up={'Up':True,'Down':False}.get(row[7]))
    if statuses.get('stations')=='ok':
        raw=pages['stations'];stations=[];result['stations']=stations;inventory=dict(online_rows=0,offline_rows=0,other_rows=0);result['inventory']=inventory
        for row in rows(raw,'stWlan',24):
            channel=num(row[13],True);v={'enabled':bit(row[1]),'channel':channel,'band':('2.4GHz' if channel and channel<=14 else '5GHz' if channel else None),'transmit_power_pct':num(row[18]),'client_limit':num(row[22],True),'bandwidth_code':num(row[17],True),'service_enabled':bit(row[19]),'hidden':bit(row[20]),'wmm_enabled':bit(row[21]),'auto_channel':bit(row[23])}
            if re.fullmatch(r'[A-Za-z0-9_+/,.-]{1,40}',row[15]):v['standard_reported']=row[15]
            wifi.setdefault(wlan(row[0]),{}).update(v)
        capabilities={10:'wmm',11:'power_save',12:'high_band',16:'80211k',17:'80211v',18:'dual_band',19:'beamforming',22:'twt_requester',23:'twt_responder',24:'bss_coloring',25:'ofdma',26:'mu_mimo',27:'80211w',28:'mimo',29:'80211r'}
        for row in rows(raw,'stAssociatedDevice',30):
            v={'interface':wlan(row[0])};identity=mac(row[1]);address=ip(row[13])
            if identity:v['mac']=identity
            if address:v['ip']=address
            if label(row[14]):v['description']=label(row[14])
            for index,key in enumerate(('uptime_seconds','rx_link_mbps','tx_link_mbps','rssi_dbm','noise_dbm_reported','snr_db_reported','signal_quality_reported'),2):
                value=num(row[index])
                if value is not None:v[key]=value
            v['capabilities']={key:bit(row[i]) for i,key in capabilities.items()}
            if re.fullmatch(r'[A-Za-z0-9_+/,.-]{1,40}',row[9]):v['working_mode_reported']=row[9]
            if re.fullmatch(r'[1-8]\*[1-8]',row[15]):v['antenna_configuration']=row[15].replace('*','x')
            stations.append(v)
        clients={}
        def get(identity):return clients.setdefault(identity,{'mac':identity,'names':[],'ips':[],'ports':[],'device_types':[],'reported_status':'Unknown'})
        def add(values,value):
            if value and value not in values and len(values)<16:values.append(value)
        for row in rows(raw,'USERDeviceInfo',10):
            inventory[{'Online':'online_rows','Offline':'offline_rows'}.get(row[4],'other_rows')]+=1
            identity=mac(row[1])
            if not identity:continue
            client=get(identity)
            for i in (6,8):add(client['names'],label(row[i]))
            for i in (3,7):add(client['device_types'],label(row[i]))
            add(client['ports'],(label(row[5])+':'+label(row[2]))[:128])
            if client['reported_status']!='Online':client['reported_status']=row[4] if row[4] in ('Online','Offline') else 'Unknown'
            if re.fullmatch(r'\d{1,10}',row[9]) and int(row[9])<=4294967295:client['lease_remaining_seconds']=max(client.get('lease_remaining_seconds',0),int(row[9]))
        for v in stations:
            if 'mac' not in v:continue
            client=get(v['mac']);client['reported_status']='Online';add(client['ips'],v.get('ip'));add(client['names'],v.get('description'));add(client['ports'],v['interface'])
        for row in rows(pages['lan'],'NeighInfo',5):
            interface=row[3].lower()
            if not(interface.startswith('internetgatewaydevice.landevice.1.') or re.fullmatch(r'(?:lan[1-4]|wlan\d+)',interface)):continue
            identity=mac(row[2]);address=ip(row[1])
            if not identity or not address:continue
            client=get(identity);add(client['ips'],address);add(client['ports'],label(row[3]));status=row[4].lower()
            if status in ('reachable','stale','delay','probe','incomplete','failed','permanent','unknown'):add(client.setdefault('neighbor_states',[]),status)
        result['clients']=list(clients.values())
    if statuses.get('wan_states')=='ok':
        result['wan_states']={}
        for row in rows(pages['wan_states'],'WanIP',63):
            v={'enabled':bit(row[9]),'nat_enabled':bit(row[18]),'ipv4_enabled':bit(row[30]),'ipv6_enabled':bit(row[31]),'services':[]}
            if row[12] in ('Connected','Connecting','Disconnected','Disconnecting','Unconfigured','PendingDisconnect','Authenticating','Error','Disabled','Up','Down'):v['connection_state']=row[12]
            for token in re.split('[, _]+',row[26].upper()):
                service={'INTERNET':'Internet','VOIP':'VoIP','IPTV':'IPTV','TR069':'Management'}.get(token)
                if service and service not in v['services']:v['services'].append(service)
            value=num(row[43],True)
            if value is not None:v['uptime_seconds']=value
            result['wan_states'][wan(row[0])]=v
    if statuses.get('wan_packets')=='ok':
        result['wan_packet_totals']={}
        for row in rows(pages['wan_packets'],'WaninfoStats',11):
            fields=('tx_bytes','rx_bytes','tx_packets','rx_packets','tx_unicast_packets','rx_unicast_packets','tx_multicast_packets','rx_multicast_packets','tx_broadcast_packets','rx_broadcast_packets')
            values={key:int(row[i]) for i,key in enumerate(fields,1)};key=wan(row[0]);result['wan_packet_totals'][key]=values
            if key in interfaces:interfaces[key].update({k:v for k,v in values.items() if k not in fields[:4]})
    if statuses.get('voice')=='ok':
        result['voice']={}
        for row in rows(pages['voice'],'stLine',6):
            v={}
            if row[3] in ('Disabled','Up','Down','Registering','Registered','Unregistered','Error','Initializing','Quiescent'):v['registration_state']=row[3]
            if row[5] in ('ERROR_NONE','NONE','ERROR_TIMEOUT','ERROR_SERVER_UNREACHABLE','ERROR_AUTHENTICATION','ERROR_AUTHENTICATION_FAILED','ERROR_SIP_REGISTRATION'):v['registration_error']=row[5]
            result['voice']['line'+re.search(r'\.Line\.(\d+)',row[0])[1]]=v
    return result

def source_check(pages,payload):
    expected=reference_payload(pages,payload.get('sections',{}));actual={k:v for k,v in payload.items() if k!='collected_at'}
    paths=differences(expected,actual)
    manifest=Counter(re.sub(r'\[\d+\]','[]',p) for p,_ in leaves(actual))
    return {'checked_values':sum(manifest.values()),'field_paths':dict(sorted(manifest.items())),'mismatches':paths,'source_pages':sorted(pages)}

def saved_check(payload):
    from . import core
    with core.connect() as db:
        row=db.execute('SELECT id,ts,payload FROM huawei_samples WHERE ts=? ORDER BY id DESC LIMIT 1',(payload['collected_at'],)).fetchone()
        if row is None:return {'mismatches':['missing_master_sample'],'checked_values':0}
        actual=json.loads(row['payload']);errors=differences(payload,actual)
        clients=db.execute('SELECT mac,ts,payload FROM router_client_samples WHERE sample_id=? ORDER BY id',(row['id'],)).fetchall()
        expected={c['mac']:{**c,'stations':[s for s in payload.get('stations',[]) if s.get('mac')==c['mac']]} for c in payload.get('clients',[])}
        count=sum(1 for _ in leaves(payload))
        if len(clients)!=len(expected):errors.append('client_row_count')
        for index,client in enumerate(clients):
            if client['ts']!=payload['collected_at']:errors.append(f'client_rows[{index}].timestamp')
            stored=json.loads(client['payload']);count+=sum(1 for _ in leaves(stored))
            errors.extend(differences(expected.get(client['mac']),stored,f'client_rows[{index}]'))
        return {'sample_id':row['id'],'checked_values':count,'client_rows':len(clients),'mismatches':errors}

class LiveAudit:
    def __init__(self,adapter,cycles=3,path='data/audit/live-verification.json'):
        self.adapter=adapter;self.remaining=cycles;self.path=Path(path);self.pages={};self.pending=None
        self.report={'started_at':datetime.now(timezone.utc).isoformat(),'raw_pages_persisted':False,'requested_cycles':cycles,'samples':[]}
        original_request=adapter._request;original_read=adapter._read_data
        def request(connection,method,url,*args,**kwargs):
            result=original_request(connection,method,url,*args,**kwargs)
            if self.remaining and method=='GET':
                from .adapters.huawei_b7 import PATHS
                key='index' if url=='/index.asp' else next((k for k,v in PATHS.items() if v==url),None)
                if key:self.pages[key]=result[0]
            return result
        def read(connection):
            self.pages.clear();payload=original_read(connection)
            if self.remaining:
                try:self.pending=source_check(self.pages,payload)
                except Exception as exc:self.pending={'checked_values':0,'mismatches':['reference_error_'+type(exc).__name__]}
            self.pages.clear();return payload
        adapter._request=request;adapter._read_data=read
    def finish(self,payload,port):
        if not self.remaining or self.pending is None:return
        from urllib.request import build_opener,ProxyHandler
        source=self.pending;self.pending=None;stored=saved_check(payload)
        api_errors=[]
        if 'sample_id' in stored:
            opener=build_opener(ProxyHandler({}))
            try:
                with opener.open(f'http://127.0.0.1:{port}/api/archive?kind=huawei&after={stored["sample_id"]-1}&limit=1',timeout=10) as response:page=json.load(response)
                api_errors=differences(payload,page['rows'][0]['payload'])
            except Exception as exc:api_errors=['archive_error_'+type(exc).__name__]
        entry={'collected_at':payload['collected_at'],'source_reference':source,'sqlite':stored,'archive_mismatches':api_errors}
        self.report['samples'].append(entry);self.remaining-=1
        self.report['completed']=self.remaining==0
        self.report['passed']=all(not (s['source_reference']['mismatches'] or s['sqlite']['mismatches'] or s['archive_mismatches']) for s in self.report['samples'])
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.report,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(self.path)
        print('Auditoria de recolha:',len(self.report['samples']),'/',self.report['requested_cycles'],'·', 'OK' if self.report['passed'] else 'DIVERGÊNCIAS')
