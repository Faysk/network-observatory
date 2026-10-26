"""Versioned, allowlisted GUI observations. No actions, secrets or WAN addresses."""
import copy
import hashlib
import ipaddress
import json
import math
import re
import http.client
from datetime import datetime, timezone

WIDTH_POLICIES={0:'Auto. 20/40 MHz',1:'20 MHz',2:'40 MHz',3:'Auto. 20/40/80 MHz',4:'Auto. 20/40/80/160 MHz',5:'80+80 MHz',6:'80 MHz'}
SOURCES={
 'radio_settings':('/html/amp/ptvdf/vdfWlanAdvNew.asp','Configuração Wi-Fi',True),
 'guest_limits':('/html/amp/ptvdf/vdfWlanAdvNew.asp','Limites da rede convidada',True),
 'upnp':('/html/bbsp/upnp/upnp_ptvdf.asp','Mapeamentos UPnP',True),
 'firewall_v4':('/html/bbsp/ipincoming/ipv4filterptvdf.asp','Firewall IPv4',True),
 'firewall_v6':('/html/bbsp/ipv6ipincoming/ipv6filterptvdf.asp','Firewall IPv6',True),
 'wan_acl':('/html/bbsp/wanacl/acl_ptvdfUser.asp','Acesso de gestão WAN',True),
 'dhcp':('/html/bbsp/common/GetLanUserDhcpInfo.asp','Concessões DHCP',False),
 'client_details':('/html/bbsp/common/GetLanUserDevInfo.asp','Detalhes dos clientes',False),
 'ipv6':('/html/bbsp/common/wan_list_cache_wanipv6.asp','Estado WAN IPv6',False),
 'wps':('/html/amp/ptvdf/getWPSData.asp','Estado WPS',True),
 'wifi_features':('/html/amp/ptvdf/mergeSSID.asp','Recursos Wi-Fi',True),
 'usb_voice':('/html/ssmp/collect/collectInfo_vdf.asp','USB, voz e hardware Wi-Fi',False),
 'lan_settings':('/html/bbsp/lansettings/lanipv4_ptvdf.asp','DHCP e encaminhamento DNS',True),
 'ipv6_lan':('/html/bbsp/lansettings/lanipv6_ptvdf.asp','Anúncio IPv6 na LAN',True),
 'topology':('/html/bbsp/common/topoinfo.asp','Topologia e portas',True),
 'radios':('/html/amp/common/wlan_list.asp','Rádios e bandas',False),
 'band_steering':('/html/amp/ptvdf/vdfBandSteering.asp','Exclusões de band steering',True),
 'wifi_schedule':('/html/amp/ptvdf/vdfScheduleNew.asp','Agendamento Wi-Fi',True),
 'mac_policy':('/html/bbsp/wlanmacfilter/vdfMacFilter.asp','Políticas de filtro MAC',True),
 'file_services':('/html/ssmp/usbftp/ftpserver_ptvdf.asp','Serviços de partilha USB',True),
 'dlna':('/html/ssmp/dlna/dlna_ptvdf.asp','Estado DLNA',True),
 'wan_nat':('/html/bbsp/dmz/dmz_ptvdf.asp','Configuração NAT por serviço WAN',True),
 'voice_schedule':('/html/voip/vdfringsch/vdfringsch.asp','Política de toque de voz',True),
 'wifi_backhaul':('/html/amp/ptvdf/vdfWlaninfo.asp','Airtime fairness e backhaul',True),
 'client_addresses':('/html/bbsp/userdevinfo/getuserdevinfo.asp','Endereços reportados por cliente',False),
 'station_details':('/html/amp/ptvdf/getassociateddeviceinfo.asp','Estações Wi-Fi · fonte alternativa',False),
 'client_modes':('/html/bbsp/common/GetLanUserDevInfo.asp','Modos Wi-Fi reportados por cliente',False),
 'guest_network':('/html/amp/ptvdf/vdfWlanAdvNew.asp','Endereçamento da rede convidada',True),
}

def utcnow():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def flag(v):return {'0':False,'1':True}.get(v.strip())
def number(v):
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',v.strip()):return None
    n=float(v)
    return (int(n) if n.is_integer() else n) if math.isfinite(n) and abs(n)<=10**15 else None
def label(v):return ''.join(c for c in v if c.isprintable()).strip()[:128]
def enum(v):return v if re.fullmatch(r'[A-Za-z0-9_+/,.-]{1,48}',v) else None
def mac(v):
    v=v.lower().replace('-',':')
    return v if re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',v) and v not in ('00:00:00:00:00:00','ff:ff:ff:ff:ff:ff') else None
def private_ip(v):
    try:
        a=ipaddress.ip_address(v)
        networks=('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16','fc00::/7','fe80::/10')
        return str(a) if any(a in ipaddress.ip_network(n) for n in networks if a.version==ipaddress.ip_network(n).version) else None
    except ValueError:return None
def ref(v):return hashlib.sha256(v.encode()).hexdigest()[:16]
def interface(domain):
    m=re.search(r'WLANConfiguration\.(\d+)',domain)
    if not m:raise ValueError('wlan_domain')
    return 'wlan'+m[1]
def rows(raw,name,arity,required=False):
    allowed={arity} if isinstance(arity,int) else set(arity)
    if len(raw)>2_000_000:raise ValueError('size')
    result=[];token=r'"(?:[^"\\]|\\.)*"'
    for m in re.finditer(r'\bnew\s+'+re.escape(name)+r'\s*\(',raw):
        a=re.match(r'(\s*'+token+r'(?:\s*,\s*'+token+r')*\s*)\)',raw[m.end():])
        if not a:continue
        values=json.loads('['+re.sub(r'\\x([0-9a-fA-F]{2})',r'\\u00\1',a[1])+']')
        if len(values) not in allowed:raise ValueError('schema_arity')
        result.append(values)
    if len(result)>512 or (required and not result):raise ValueError('schema_rows')
    return result

def parse(source,raw):
    out=[]
    if source=='radio_settings':
        nr={6:'channel_reported',7:'power_pct',10:'width_policy_code',16:'mcs_setting',17:'rssi_threshold_setting',19:'channel_plus_setting'}
        bf={2:'enabled',4:'hidden',9:'auto_channel',11:'wmm',13:'pmf',14:'beamforming',15:'ocac',18:'rssi_threshold_enabled',20:'scs',21:'periodic_auto_channel',24:'qhop',30:'service_enabled'}
        for r in rows(raw,'stWlanWifi',32,True):
            item={'interface':interface(r[0]),'standard_reported':enum(r[5]),'work_mode_reported':enum(r[12]),'auto_channel_scope_reported':enum(r[22]),'pmf_policy_reported':enum(r[13]),'wifi_mode_reported':enum(r[23]),'beacon_type_reported':enum(r[25]),'basic_encryption_reported':enum(r[26]),'wpa_encryption_reported':enum(r[27]),'ieee_encryption_reported':enum(r[28]),'mixed_encryption_reported':enum(r[29]),'rekey_interval_reported':number(r[31])}
            item.update({k:number(r[i]) for i,k in nr.items()});item.update({k:flag(r[i]) for i,k in bf.items()});out.append(item)
        for name,n,fields,types in [('stWlanAdv',5,['dtim_setting','beacon_setting','rts_threshold','frag_threshold'],[number]*4),('stAttachConf',5,['airtime_fairness','channel_scope','mu_mimo_enabled','preamble_setting'],[flag,flag,flag,enum])]:
            for r in rows(raw,name,n):
                item=next((v for v in out if v['interface']==interface(r[0])),None)
                if item is not None:item.update({k:fn(r[i+1]) for i,(k,fn) in enumerate(zip(fields,types))})
    elif source=='guest_limits':
        out=[{'slot':i+1,'upload_limit_reported':number(r[1]),'download_limit_reported':number(r[2])} for i,r in enumerate(rows(raw,'stGuestLimitInfo',3,True))]
    elif source=='guest_network':
        out=[{'slot':i+1,'pool_start_ip':private_ip(r[1]),'pool_end_ip':private_ip(r[2]),'source_interface_ref':ref(r[3])} for i,r in enumerate(rows(raw,'stGuestIpInfo',4,True))]
    elif source=='upnp':
        if not re.search(r'function\s+stUpnpPortMapping\s*\(',raw):raise ValueError('upnp_schema')
        for r in rows(raw,'stUpnpPortMapping',8):
            if r[0]!='1' and r[3] in ('','0') and r[4] in ('','0') and not r[5] and r[6] in ('','0.0.0.0'):continue
            if r[5].upper() not in ('TCP','UDP') or not r[3].isdigit() or not r[4].isdigit() or not 1<=int(r[3])<=65535 or not 1<=int(r[4])<=65535:raise ValueError('mapping_schema')
            out.append({'enabled':flag(r[0]),'lease_seconds_reported':number(r[1]),'remote_restricted':r[2] not in ('','0.0.0.0','::'),
                'external_port':int(r[3]),'internal_port':int(r[4]),'protocol':r[5].upper(),'client_ip':private_ip(r[6]),'description':label(r[7])})
    elif source in ('firewall_v4','firewall_v6'):
        out=[dict(zip(('right_code','policy_code','level_code'),map(enum,r[1:]))) for r in rows(raw,'stPortFilter',4,True)]
    elif source=='wan_acl':
        if 'function WanAccessItemClass' not in raw:raise ValueError('acl_schema')
        out=[{'enabled':flag(r[1]),'protocol_code':enum(r[2]),'wan_ref':ref(r[3]),'source_restricted':r[4] not in ('','0.0.0.0/0','::/0')} for r in rows(raw,'WanAccessItemClass',5)]
    elif source=='dhcp':
        if not re.search(r'function\s+DHCPInfo\s*\(',raw):raise ValueError('dhcp_schema')
        out=[{'mac':mac(r[3]),'name':label(r[1]),'ip':private_ip(r[2]),'lease_remaining_seconds':number(r[4]),'type_reported':label(r[5]),'interface_reported':enum(r[6]),'address_source_reported':enum(r[7]),'lease_elapsed_reported_seconds':number(r[8])} for r in rows(raw,'DHCPInfo',9) if mac(r[3])]
    elif source=='client_details':
        seen={}
        for r in rows(raw,'USERDevice',(16,17),True):
            identity=mac(r[2])
            if not identity:continue
            item={'mac':identity,'ip':private_ip(r[1]),'port_reported':label(r[3]),'ip_type_reported':enum(r[4]),'type_reported':label(r[5]),'status_reported':enum(r[6]),'port_type_reported':enum(r[7]),'time_reported':number(r[8]),'name':label(r[9]),'ipv4_enabled':flag(r[10]),'ipv6_enabled':flag(r[11]),'category_reported':label(r[12]),'alias':label(r[13]),'manual_type_reported':label(r[14]),'lease_remaining_seconds':number(r[15])}
            if identity in seen and seen[identity]!=item:raise ValueError('ambiguous_inventory_branches')
            seen[identity]=item
        out=list(seen.values())
    elif source=='ipv6':
        for i,r in enumerate(rows(raw,'IPv6WanInfo',12,True)):
            out.append({'slot':i+1,'type_reported':enum(r[1]),'connection_state':enum(r[2]),'encapsulation_reported':enum(r[3]),'dns_present':bool(r[7]),'aftr_present':bool(r[8] or r[9]),'gateway_present':bool(r[10]),'uptime_seconds_reported':number(r[11])})
        for kind,name,n in [('address','IPv6AddressInfo',7),('prefix','IPv6PrefixInfo',6)]:
            for i,r in enumerate(rows(raw,name,n)):
                start=4 if kind=='address' else 3
                out.append({'slot':i+1,'kind':kind,'origin_reported':enum(r[2] if kind=='address' else r[1]),'present':bool(r[3] if kind=='address' else r[2]),'preferred_seconds_reported':number(r[start]),'valid_seconds_reported':number(r[start+1]),'remaining_seconds_reported':number(r[start+2])})
    elif source=='wps':
        out=[{'interface':interface(r[0]),'enabled':flag(r[1]),'method_reported':enum(r[2])} for r in rows(raw,'stWpsPin',3,True)]
    elif source=='wifi_features':
        m=re.search(r'\bvar\s+mloEnable\s*=\s*["\x27]([01])["\x27]',raw)
        if not m:raise ValueError('mlo_schema')
        out=[{'mlo_enabled':flag(m[1])}]
    elif source=='usb_voice':
        for i,r in enumerate(rows(raw,'stPhysicalMedium',4)):
            out.append({'kind':'usb','slot':i+1,'status_reported':enum(r[2]),'safe_remove_reported':flag(r[3])})
        for i,r in enumerate(rows(raw,'stLine',6)):
            out.append({'kind':'voice','slot':i+1,'registration_state':enum(r[3]),'call_state_reported':enum(r[4]),'registration_error':enum(r[5])})
        for name,band in [('wlanChipType2G','2.4GHz'),('wlanChipType5G','5GHz')]:
            m=re.search(r'\bvar\s+'+name+r'\s*=\s*["\x27]([A-Za-z0-9_.-]{1,48})["\x27]',raw)
            if m:out.append({'kind':'wifi_hardware','band':band,'component_reported':m[1]})
        if not out:raise ValueError('health_schema')
    elif source=='lan_settings':
        for r in rows(raw,'stMainDhcpInfo',7,True):out.append({'kind':'dhcp_server','enabled':flag(r[1]),'pool_start_ip':private_ip(r[2]),'pool_end_ip':private_ip(r[3]),'lease_duration_seconds_reported':number(r[4]),'dns_override_present':bool(r[6])})
        for i,r in enumerate(rows(raw,'stDnsRelForwardingInfo',8)):
            out.append({'kind':'dns_forwarding','slot':i+1,'enabled':flag(r[1]),'status_reported':enum(r[2]),'server_present':bool(r[4]),'type_reported':enum(r[6]),'override_allowed':flag(r[7])})
        for i,r in enumerate(rows(raw,'stLanHostInfo',4)):
            out.append({'kind':'lan_address','slot':i+1,'enabled':flag(r[1]),'ip':private_ip(r[2]),'subnet_mask':enum(r[3])})
        for r in rows(raw,'stDhcpStaticInfo',3):
            if mac(r[2]):out.append({'kind':'dhcp_reservation','ip':private_ip(r[1]),'mac':mac(r[2])})
    elif source=='ipv6_lan':
        out=[{'managed':flag(r[1]),'other_config':flag(r[2]),'enabled':flag(r[3])} for r in rows(raw,'stRouterAdver',4,True)]
        for r in rows(raw,'stIpv6DNSConfig',3):out.append({'kind':'dns','type_reported':enum(r[1]),'server_present':bool(r[2])})
    elif source=='topology':
        out=[{'slot':i+1,'l3_enabled':flag(r[2]),'mode_reported':enum(r[3]),'vlan_reported':number(r[4]),'multicast_vlan_enabled':flag(r[5]),'multicast_vlan_reported':number(r[6])} for i,r in enumerate(rows(raw,'LanInfoClass',7,True))]
    elif source=='radios':
        out=[{'slot':i+1,'band':enum(r[1]),'enabled':flag(r[2])} for i,r in enumerate(rows(raw,'stRadio',3,True))]
    elif source=='band_steering':
        if 'function stDisallowSta' not in raw:raise ValueError('steering_schema')
        out=[{'mac':mac(r[2])} for r in rows(raw,'stDisallowSta',3) if mac(r[2])]
    elif source=='wifi_schedule':
        if 'function stDuration' not in raw:raise ValueError('schedule_schema')
        out=[{'slot':i+1,'start_reported':r[1] if re.fullmatch(r'[0-9:]{1,16}',r[1]) else None,'end_reported':r[2] if re.fullmatch(r'[0-9:]{1,16}',r[2]) else None,'repeat_days_code':enum(r[3]),'enabled':flag(r[4]),'ssid_mask_code':enum(r[5])} for i,r in enumerate(rows(raw,'stDuration',7))]
    elif source=='mac_policy':
        out=[dict(zip(('filter_right','filter_policy','wlan_filter_right','wlan_filter_policy'),map(enum,r[1:]))) for r in rows(raw,'stMacFilterArr',5,True)]
    elif source=='file_services':
        for r in rows(raw,'stFtpSrvCfg',7):out.append({'kind':'ftp','enabled':flag(r[1]),'port':number(r[3]),'user_count':number(r[5]),'share_all':flag(r[6])})
        for r in rows(raw,'stSftpSrvCfg',4):out.append({'kind':'sftp','enabled':flag(r[1]),'port':number(r[2]),'wan_enabled':flag(r[3])})
        if not out:raise ValueError('file_service_schema')
    elif source=='dlna':
        out=[{'enabled':flag(r[1]),'share_all':flag(r[2])} for r in rows(raw,'stDlnaService',4,True)]
    elif source=='wan_nat':
        out=[{'slot':i+1,'wan_ref':ref(r[0]),'services_reported':enum(r[2]),'nat_enabled':flag(r[3]),'ipv4_enabled':flag(r[5]),'connection_type_reported':enum(r[6])} for i,r in enumerate(rows(raw,'stWANInfo',7,True))]
    elif source=='voice_schedule':
        out=[{'enabled':flag(r[1]),'policy_code':enum(r[2])} for r in rows(raw,'stRingSchedule',3,True)]
    elif source=='wifi_backhaul':
        out=[{'interface':interface(r[0]),'airtime_fairness':flag(r[1]),'backhaul_reported':enum(r[2])} for r in rows(raw,'stAttachConf',3,True)]
    elif source=='client_addresses':
        # The consumer declares nine fields; the three extra arguments are deliberately discarded.
        seen=set()
        for r in rows(raw,'stUserDevInfoPTVDF',12,True):
            if not mac(r[3]):continue
            item={'name':label(r[0]),'type_reported':label(r[1]),'ip':private_ip(r[2]),'mac':mac(r[3]),'status_reported':enum(r[4]),'port_reported':label(r[5]),'time_reported':number(r[6]),'lease_reported':number(r[7])}
            key=json.dumps(item,sort_keys=True)
            if key not in seen:seen.add(key);out.append(item)
    elif source=='client_modes':
        out=[{'work_mode_reported':enum(r[1]),'ip':private_ip(r[2]),'mac':mac(r[3])} for r in rows(raw,'stWifiWorkingMode',4,True) if mac(r[3])]
    elif source=='station_details':
        if not re.search(r'function\s+stAssociatedDevice\s*\(',raw):raise ValueError('station_schema')
        numeric={2:'uptime_seconds_reported',3:'rx_link_mbps',4:'tx_link_mbps',5:'rssi_dbm',6:'noise_dbm_reported',7:'snr_db_reported',8:'signal_quality_reported'}
        flags={10:'wmm',11:'power_save',12:'high_band',16:'supports_11k',17:'supports_11v',18:'dual_band',19:'beamforming',21:'twt_requester',22:'twt_responder',23:'bss_coloring',24:'ofdma',25:'mu_mimo',26:'supports_11w',27:'mimo',28:'supports_11r'}
        for r in rows(raw,'stAssociatedDevice',29):
            if not mac(r[1]):continue
            item={'interface':interface(r[0]),'mac':mac(r[1]),'ip':private_ip(r[13]),'description':label(r[14]),'work_mode_reported':enum(r[9]),'resource_unit_reported':enum(r[20])}
            item.update({key:number(r[i]) for i,key in numeric.items()});item.update({key:flag(r[i]) for i,key in flags.items()});out.append(item)
    else:raise ValueError('unknown_source')
    validate_rows(source,out)
    return out

# Field allowlists are also applied at ingestion, not just by the parser.
FIELDS={
 'radio_settings':'interface standard_reported work_mode_reported auto_channel_scope_reported channel_reported power_pct width_policy_code mcs_setting rssi_threshold_setting channel_plus_setting enabled hidden auto_channel wmm pmf beamforming ocac rssi_threshold_enabled scs periodic_auto_channel qhop service_enabled dtim_setting beacon_setting rts_threshold frag_threshold airtime_fairness channel_scope mu_mimo_enabled preamble_setting',
 'guest_limits':'slot upload_limit_reported download_limit_reported',
 'upnp':'enabled lease_seconds_reported remote_restricted external_port internal_port protocol client_ip description',
 'firewall_v4':'right_code policy_code level_code','firewall_v6':'right_code policy_code level_code',
 'wan_acl':'enabled protocol_code wan_ref source_restricted',
 'dhcp':'mac name ip lease_remaining_seconds type_reported interface_reported address_source_reported lease_elapsed_reported_seconds',
 'client_details':'mac ip port_reported ip_type_reported type_reported status_reported port_type_reported time_reported name ipv4_enabled ipv6_enabled category_reported alias manual_type_reported lease_remaining_seconds',
 'ipv6':'slot type_reported connection_state encapsulation_reported dns_present aftr_present gateway_present uptime_seconds_reported kind origin_reported present preferred_seconds_reported valid_seconds_reported remaining_seconds_reported',
 'wps':'interface enabled method_reported','wifi_features':'mlo_enabled',
 'usb_voice':'kind slot status_reported safe_remove_reported registration_state call_state_reported registration_error band component_reported',
 'lan_settings':'kind enabled lease_duration_seconds_reported dns_override_present slot status_reported server_present type_reported override_allowed ip mac subnet_mask',
 'ipv6_lan':'managed other_config enabled kind type_reported server_present','topology':'slot l3_enabled mode_reported vlan_reported multicast_vlan_enabled multicast_vlan_reported',
 'radios':'slot band enabled','band_steering':'mac','wifi_schedule':'slot start_reported end_reported repeat_days_code enabled ssid_mask_code',
 'mac_policy':'filter_right filter_policy wlan_filter_right wlan_filter_policy','file_services':'kind enabled port user_count share_all wan_enabled','dlna':'enabled share_all',
 'wan_nat':'slot wan_ref services_reported nat_enabled ipv4_enabled connection_type_reported',
 'voice_schedule':'enabled policy_code','wifi_backhaul':'interface airtime_fairness backhaul_reported',
 'client_addresses':'name type_reported ip mac status_reported port_reported time_reported lease_reported',
 'station_details':'interface mac ip description work_mode_reported resource_unit_reported uptime_seconds_reported rx_link_mbps tx_link_mbps rssi_dbm noise_dbm_reported snr_db_reported signal_quality_reported wmm power_save high_band supports_11k supports_11v dual_band beamforming twt_requester twt_responder bss_coloring ofdma mu_mimo supports_11w mimo supports_11r',
}
FIELDS['radio_settings']+=' pmf_policy_reported wifi_mode_reported beacon_type_reported basic_encryption_reported wpa_encryption_reported ieee_encryption_reported mixed_encryption_reported rekey_interval_reported'
FIELDS['lan_settings']+=' pool_start_ip pool_end_ip'
FIELDS['guest_network']='slot pool_start_ip pool_end_ip source_interface_ref'
FIELDS['client_modes']='work_mode_reported ip mac'
BOOLS=set('enabled hidden auto_channel wmm pmf beamforming ocac rssi_threshold_enabled scs periodic_auto_channel qhop service_enabled airtime_fairness channel_scope mu_mimo_enabled remote_restricted source_restricted ipv4_enabled ipv6_enabled dns_present aftr_present gateway_present present mlo_enabled safe_remove_reported dns_override_present server_present override_allowed managed other_config l3_enabled multicast_vlan_enabled share_all wan_enabled'.split())
BOOLS.add('nat_enabled')
BOOLS.update('power_save high_band supports_11k supports_11v dual_band twt_requester twt_responder bss_coloring ofdma mu_mimo supports_11w mimo supports_11r'.split())
NUMBERS=set('slot channel_reported power_pct width_policy_code mcs_setting rssi_threshold_setting channel_plus_setting dtim_setting beacon_setting rts_threshold frag_threshold upload_limit_reported download_limit_reported lease_seconds_reported external_port internal_port lease_remaining_seconds lease_elapsed_reported_seconds time_reported uptime_seconds_reported preferred_seconds_reported valid_seconds_reported remaining_seconds_reported lease_duration_seconds_reported vlan_reported multicast_vlan_reported port user_count'.split())
NUMBERS.update('lease_reported rx_link_mbps tx_link_mbps rssi_dbm noise_dbm_reported snr_db_reported signal_quality_reported'.split())
NUMBERS.add('rekey_interval_reported')
LABELS=set('name alias description type_reported port_reported category_reported manual_type_reported'.split())
def validate_rows(source,data):
    if source not in FIELDS or not isinstance(data,list) or len(data)>512:raise ValueError('observation_rows')
    allowed=set(FIELDS[source].split())
    for row in data:
        if not isinstance(row,dict) or set(row)-allowed:raise ValueError('observation_fields')
        for k,v in row.items():
            if v is None:continue
            if k in BOOLS:ok=type(v) is bool
            elif k in NUMBERS:ok=type(v) in (int,float) and math.isfinite(v) and abs(v)<=10**15
            elif k=='mac':ok=isinstance(v,str) and mac(v)==v
            elif k in ('ip','client_ip','pool_start_ip','pool_end_ip'):ok=isinstance(v,str) and private_ip(v)==v
            elif k in LABELS:ok=isinstance(v,str) and len(v)<=128 and label(v)==v
            else:ok=isinstance(v,str) and len(v)<=48 and bool(re.fullmatch(r'[A-Za-z0-9_+/:,.-]*',v))
            if ok and k in ('power_pct','signal_quality_reported'):ok=0<=v<=100
            if ok and k=='channel_reported':ok=type(v) is int and 0<=v<=233
            if ok and k in ('external_port','internal_port'):ok=type(v) is int and 1<=v<=65535
            if ok and k=='port':ok=type(v) is int and 0<=v<=65535
            if ok and k in ('rssi_dbm','noise_dbm_reported'):ok=-200<=v<=0
            if ok and k in ('rx_link_mbps','tx_link_mbps'):ok=0<=v<=100000
            if not ok:raise ValueError('observation_value')

def validate(bundle):
    if not isinstance(bundle,dict) or set(bundle)-set(SOURCES):raise ValueError('observation_sources')
    for source,item in bundle.items():
        if not isinstance(item,dict) or set(item)!={'collected_at','status','reason','data'}:raise ValueError('observation_contract')
        ts=datetime.fromisoformat(item['collected_at'])
        if ts.tzinfo is None or (ts-datetime.now(timezone.utc)).total_seconds()>5:raise ValueError('observation_time')
        if item['status'] not in ('ok','unavailable'):raise ValueError('observation_status')
        if item['reason'] not in (None,'schema','transport','http','authentication','budget'):raise ValueError('observation_reason')
        if item['status']=='ok':
            if item['reason'] is not None:raise ValueError('successful_reason')
            validate_rows(source,item['data'])
        elif item['data'] is not None:raise ValueError('unavailable_data')

def collect(adapter,conn):
    now=adapter.clock()
    if adapter.observation_cache is not None and now<adapter.next_observation_attempt:return copy.deepcopy(adapter.observation_cache)
    pages={};result={}
    for source,(path,title,tracked) in SOURCES.items():
        stamp=utcnow()
        if adapter.clock()-now>=30:
            result[source]={'collected_at':stamp,'status':'unavailable','reason':'budget','data':None}
            continue
        try:
            if path not in pages:
                try:pages[path]=adapter._request(conn,'GET',path,cookie=adapter.cookie)[0]
                except adapter.authentication_error:raise
                except Exception as exc:pages[path]=exc
            if isinstance(pages[path],Exception):raise pages[path]
            data=parse(source,pages[path]);result[source]={'collected_at':stamp,'status':'ok','reason':None,'data':data}
        except adapter.authentication_error:
            raise
        except (OSError,http.client.HTTPException):
            conn.close();result[source]={'collected_at':stamp,'status':'unavailable','reason':'transport','data':None}
        except Exception as exc:
            reason='http' if exc.args==('router_http_error',) else 'schema'
            result[source]={'collected_at':stamp,'status':'unavailable','reason':reason,'data':None}
    adapter.next_observation_attempt=now+300
    adapter.observation_cache=copy.deepcopy(result)
    return result

def init_db(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS router_observations(id INTEGER PRIMARY KEY,source TEXT NOT NULL,ts TEXT NOT NULL,status TEXT NOT NULL,reason TEXT,payload TEXT,UNIQUE(source,ts));
    CREATE INDEX IF NOT EXISTS router_observations_source ON router_observations(source,ts DESC,id DESC);
    CREATE INDEX IF NOT EXISTS router_observations_cursor ON router_observations(source,id);
    CREATE TABLE IF NOT EXISTS router_changes(id INTEGER PRIMARY KEY,source TEXT NOT NULL,previous_at TEXT NOT NULL,observed_at TEXT NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL,crosses_gap INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS router_changes_time ON router_changes(observed_at,id);''')

def stable(data,source):
    ignored={'lease_seconds_reported'} if source=='upnp' else set()
    normalized=[{k:v for k,v in row.items() if k not in ignored} for row in data]
    return sorted(normalized,key=lambda x:json.dumps(x,sort_keys=True))

def persist(db,bundle,historical=False):
    for source,item in bundle.items():
        existing=db.execute('SELECT status,reason,payload FROM router_observations WHERE source=? AND ts=?',(source,item['collected_at'])).fetchone()
        if existing:
            stored=json.loads(existing['payload']) if existing['payload'] is not None else None
            if (existing['status'],existing['reason'],stored)!=(item['status'],item['reason'],item['data']):raise ValueError('Conflicting source snapshot')
            continue
        last=db.execute('SELECT ts,status FROM router_observations WHERE source=? ORDER BY ts DESC,id DESC LIMIT 1',(source,)).fetchone()
        previous=db.execute("SELECT ts,payload FROM router_observations WHERE source=? AND status='ok' ORDER BY ts DESC,id DESC LIMIT 1",(source,)).fetchone()
        if item['status']=='ok' and previous and not historical and item['collected_at']>previous['ts'] and SOURCES[source][2]:
            old=stable(json.loads(previous['payload']),source);new=stable(item['data'],source)
            if old!=new:
                gap=last['status']!='ok' or (datetime.fromisoformat(item['collected_at'])-datetime.fromisoformat(previous['ts'])).total_seconds()>900
                fields={k for row in old+new for k in row}
                detail={'before_count':len(old),'after_count':len(new),'changed_fields':sorted(k for k in fields if sorted(json.dumps(r.get(k),sort_keys=True) for r in old)!=sorted(json.dumps(r.get(k),sort_keys=True) for r in new))}
                if source=='upnp':
                    identity=lambda r:(r.get('protocol'),r.get('external_port'),r.get('internal_port'),r.get('client_ip'))
                    a={identity(r):r for r in old};b={identity(r):r for r in new}
                    detail.update(added=len(b.keys()-a.keys()),removed=len(a.keys()-b.keys()),modified=sum(a[k]!=b[k] for k in a.keys()&b.keys()))
                db.execute('INSERT INTO router_changes(source,previous_at,observed_at,kind,detail,crosses_gap) VALUES(?,?,?,?,?,?)',(source,previous['ts'],item['collected_at'],'observed_state_changed',json.dumps(detail),int(gap)))
        db.execute('INSERT INTO router_observations(source,ts,status,reason,payload) VALUES(?,?,?,?,?)',(source,item['collected_at'],item['status'],item['reason'],json.dumps(item['data'],allow_nan=False) if item['status']=='ok' else None))

def read(db,hours=24):
    hours=float(hours)
    if not math.isfinite(hours) or not 0<hours<=24*366:raise ValueError('observation_period')
    now=datetime.now(timezone.utc);cutoff=datetime.fromtimestamp(now.timestamp()-hours*3600,timezone.utc).isoformat();sources=[]
    for source,(_,title,tracked) in SOURCES.items():
        attempt=db.execute('SELECT * FROM router_observations WHERE source=? ORDER BY ts DESC,id DESC LIMIT 1',(source,)).fetchone()
        good=db.execute("SELECT * FROM router_observations WHERE source=? AND status='ok' ORDER BY ts DESC,id DESC LIMIT 1",(source,)).fetchone()
        age=max(0,int((now-datetime.fromisoformat(good['ts'])).total_seconds())) if good else None
        quality='ok' if attempt and attempt['status']=='ok' and age is not None and age<=900 else 'stale' if good else 'unavailable'
        sources.append({'id':source,'title':title,'quality':quality,'attempt_status':attempt['status'] if attempt else 'not_collected','reason':attempt['reason'] if attempt else None,'collected_at':good['ts'] if good else None,'age_seconds':age,'data':json.loads(good['payload']) if good else None,'tracks_changes':tracked})
    changes=[dict(r) for r in db.execute('SELECT * FROM router_changes WHERE observed_at>=? ORDER BY observed_at DESC,id DESC LIMIT 501',(cutoff,))]
    for row in changes:row['detail']=json.loads(row['detail']);row['crosses_gap']=bool(row['crosses_gap'])
    return {'sources':sources,'changes':changes[:500],'changes_truncated':len(changes)>500,'hours':hours,'poll_seconds':300,
        'width_policies':WIDTH_POLICIES,'semantics':{'changes':'differences observed between readings; not exact action times or causes','dhcp_elapsed':'reported elapsed current lease; not device online duration','width':'configured policy, not instantaneous channel width'},
        'unsupported':{'wifi_logs':'Exportação não disponível na interface da conta verificada; nenhuma geração automática.','neighbor_scan':'Operação ativa; não executada.','per_client_internet_bytes':'Sem contador validado.','nat_flows':'Sem tabela de fluxos validada.'}}


def archive(db,source,after=0,limit=100):
    after=int(after);limit=int(limit)
    if source not in SOURCES or not 0<=after<=2**63-1 or not 1<=limit<=500:raise ValueError('observation_cursor')
    records=[dict(r) for r in db.execute('SELECT * FROM router_observations WHERE source=? AND id>? ORDER BY id LIMIT ?',(source,after,limit+1))]
    more=len(records)>limit;records=records[:limit]
    for item in records:
        raw=item.pop('payload');item['data']=json.loads(raw) if raw is not None else None
    return {'source':source,'records':records,'has_more':more,'next_after':records[-1]['id'] if records else after}


def read_change(db,change_id):
    change_id=int(change_id)
    if not 1<=change_id<=2**63-1:raise ValueError('change_id')
    row=db.execute('SELECT * FROM router_changes WHERE id=?',(change_id,)).fetchone()
    if row is None:return None
    result=dict(row);result['detail']=json.loads(result['detail']);result['crosses_gap']=bool(result['crosses_gap'])
    for field,ts in [('before',row['previous_at']),('after',row['observed_at'])]:
        snapshot=db.execute('SELECT payload FROM router_observations WHERE source=? AND ts=?',(row['source'],ts)).fetchone()
        result[field]=json.loads(snapshot['payload']) if snapshot and snapshot['payload'] is not None else None
    return result
