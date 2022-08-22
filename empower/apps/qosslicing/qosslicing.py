#!/usr/bin/env python3
#
# Copyright (c) 2019 Roberto Riggio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.


"""
Made By: Sri Harsh Amur
Contact: sriharshamur@gmail.com
"""


"""QoS Slicing Application."""

from datetime import datetime
from tracemalloc import Statistic
from typing import Protocol

from construct import Struct, Int8ub, Int16ub, Int32ub, Bytes, Array
from construct import Container

import empower.managers.ranmanager.lvapp as lvapp

from empower_core.ssid import WIFI_NWID_MAXSIZE
from empower_core.etheraddress import EtherAddress
from empower.managers.ranmanager.lvapp.wifiapp import EWiFiApp
from empower_core.app import EVERY

from empower.managers.ranmanager.lvapp.wifislice import WiFiSlice


"""
Start from the loop function. Loop function calls sends teh DSCP Stat request periodically, After that the response is received by the handle_response function. 
Handle_response function calls the make_traffic_rule function which creates the slice and the traffic rules. 
"""


# Every packet needs a header so that the WTP can identify which packet this is and what its functionality is. 
# These headers are also defined in the WTP and need to match for the whole system to work. 
PT_WIFI_DSCP_STATS_REQUEST = 0x8D
PT_WIFI_DSCP_STATS_RESPONSE = 0x8E
PT_WIFI_TRAFFIC_RULES_RESPONSE = 0x8F  # This is techinically not a response

# This is the request sent from the controller to the WTPs for DSCP stats
WIFI_DSCP_STATS_REQUEST = Struct(
    "version" / Int8ub,
    "type" / Int8ub,
    "length" / Int32ub,
    "seq" / Int32ub,
    "xid" / Int32ub,
    "device" / Bytes(6),  # wtp, esencially a mac address
    "ssid" / Bytes(WIFI_NWID_MAXSIZE + 1),
)
WIFI_DSCP_STATS_REQUEST.name = "wifi_dscp_stats_request"

# DSCP Stat contains the packet feature 
DSCP_STATS_ENTRY = Struct(
    "src_ip" / Array(4, Int8ub),
    "dst_ip" / Array(4, Int8ub),
    "src_port" / Int16ub,
    "dst_port" / Int16ub,
    "protocol" / Int8ub,
    "dscp" / Int8ub
)
DSCP_STATS_ENTRY.name = "dscp_stats_entry"

# DSCP Stat contains the dscp code with the total count and average packet size
DSCP_MAP_ENTRY = Struct(
    "code" / Int8ub,
    "count" / Int32ub,
    "avg_packet_size" / Int32ub
)
DSCP_MAP_ENTRY.name = "dscp_map_entry"

# This is the DSCP Stat Response which contains the Packet feature details and also the details for each DSCP 
WIFI_DSCP_STATS_RESPONSE = Struct(
    "version" / Int8ub,
    "type" / Int8ub,
    "length" / Int32ub,
    "seq" / Int32ub,
    "xid" / Int32ub,
    "device" / Bytes(6),
    "ssid" / Bytes(WIFI_NWID_MAXSIZE + 1),
    "nb_entries" / Int16ub,
    "dscp_map_count" / Int8ub,
    "stats" / Array(lambda ctx: ctx.nb_entries, DSCP_STATS_ENTRY),
    "dscp_map" / Array(lambda ctx: ctx.dscp_map_count, DSCP_MAP_ENTRY)
)
WIFI_DSCP_STATS_RESPONSE.name = "wifi_dscp_stats_response"

# Traffic Rule Match Object in form of a packet
TRAFFIC_RULE_MATCH = Struct(
    "src_ip" / Array(4, Int8ub),
    "dst_ip" / Array(4, Int8ub),
    "src_port" / Int16ub,
    "dst_port" / Int16ub,
    "protocol" / Int8ub,
    "dscp" / Int8ub
)
TRAFFIC_RULE_MATCH.name = "traffic_rule_match"

# This is the traffic rule packet sent to each WTP. Each Traffic Rule packet can only contain one rule. The main detail is the dscp and the traffic rule  match object
WIFI_TRAFFIC_RULE_RESPONSE = Struct(
    "version" / Int8ub,
    "type" / Int8ub,
    "length" / Int32ub,
    "seq" / Int32ub,
    "xid" / Int32ub,
    "device" / Bytes(6),
    "dscp" / Int8ub,
    "match" / TRAFFIC_RULE_MATCH
)
WIFI_TRAFFIC_RULE_RESPONSE.name = "wifi_traffic_rules_response"


ACTIVATION_THRESHOLD = 200  # nr of pkts after which flow will be moved from BE Slice to a Group Slice
INDIVIDUAL_SLICE = 600 # nr of pakts after which flow will be moved from Group Slice to its own DSCP Slice
ANY_IP_ADDRESS = [0, 0, 0, 0] # Use this IP Address if you want all packets to match
ANY_PORT = 0 # All packets will match with this port number
ANY_PROTOCOL = 255 # You get the idea.
ANY_DSCP = 255


class DSCPStats(EWiFiApp):
    """
    QoS Slicing App.

    This app collects the dscp statistics to make traffic rules and dynamically create slices.

    Parameters:
        every: the loop period in ms (optional, default 2000ms)

    }
    """

    def __init__(self, context, service_id, every=EVERY):

        super().__init__(context=context,
                         service_id=service_id,
                         every=every)

        # Register messages
        lvapp.register_message(PT_WIFI_DSCP_STATS_REQUEST,
                               WIFI_DSCP_STATS_REQUEST)
        lvapp.register_message(PT_WIFI_DSCP_STATS_RESPONSE,
                               WIFI_DSCP_STATS_RESPONSE)
        lvapp.register_message(PT_WIFI_TRAFFIC_RULES_RESPONSE,
                               WIFI_TRAFFIC_RULE_RESPONSE)

        # Data structures
        self.stats = {}
        self.traffic_rules = {}
        self.wtps_count = 0

    def __eq__(self, other):
        if isinstance(other, DSCPStats):
            return self.every == other.every
        return False

    def to_dict(self):
        """Return JSON-serializable representation of the object."""

        out = super().to_dict()
        out['stats'] = self.stats

        return out

    def set_slices(self, dscp, quantum):
        """Sets Slices in the WTPs"""
        properties = {
            "quantum": quantum
        }
        self.context.upsert_wifi_slice(slice_id=dscp, properties=properties)

    def del_slices(self, dscp):
        """Delets Slices in the WTPs"""
        self.context.delete_wifi_slice(slice_id=dscp)

    def send_traffic_rules(self, traffic_rules):
        """Send out Traffic Rules to the WTPs"""
        for wtp in self.wtps.values():

            if not wtp.connection:
                continue

            for tr in traffic_rules:
                msg = Container(length=WIFI_TRAFFIC_RULE_RESPONSE.sizeof(),
                                dscp=tr["dscp"],
                                match=tr["match"])

                wtp.connection.send_message(PT_WIFI_TRAFFIC_RULES_RESPONSE,
                                            msg)

    def check_traffic_rule_exists(self, tr):
        match = tr["match"]
        # improve the hash function
        key = self.get_hash_match(match)

        if key in self.traffic_rules:
            # print("match exists")
            tr_dscp = tr["dscp"]
            if tr_dscp == self.traffic_rules[key]:
                # print("It is the same traffic rule")
                return True
            else:
                # print("The action dscp has changed")
                self.traffic_rules[key] = tr_dscp
                return False
        else:
            # print("New Traffic rule")
            self.traffic_rules[key] = tr["dscp"]
            return False

    def make_traffic_rules(self):
        "Makes the Traffic Rule for all WTPs"
        # Ensure DSCP stats from all WTPs have arrived before making the rule
        if len(self.stats) != self.wtps_count:
            return

        # dscpMap would hold the dscp code and the total number of such packets in the wifi network
        dscpMap = {}
        for wtp in self.stats:
            stat = self.stats[wtp]
            # print("stat: ", stat)
            for code in stat["dscp_map"]:
                # count = stat["dscp_map"].code
                if code not in dscpMap:
                    dscpMap[code] = stat["dscp_map"][code]
                else:
                    dscpMap[code] += stat["dscp_map"][code]
        print("DSCPMap: ", dscpMap)
        # Packet Size in bits * packets per second = Datarate..Actual throughput would be (payload size x packet per sec)
        traffic_rules = []
        slices = []
        for dscp in dscpMap:
            packet_count = dscpMap[dscp][0]
            if packet_count > ACTIVATION_THRESHOLD:
                if packet_count > INDIVIDUAL_SLICE:
                    # Make a slice for this particular dscp
                    tos = self.get_tos(dscp)
                    dscp_slice = dscp
                else:
                    # Change dscp into group dscp
                    dscp_slice = self.get_dscp_group(dscp)
                    tos = self.get_tos(dscp_slice)
                
                match = {
                    "src_ip": ANY_IP_ADDRESS,
                    "dst_ip": ANY_IP_ADDRESS,
                    "src_port": ANY_PORT,
                    "dst_port": ANY_PORT,
                    "protocol": ANY_PROTOCOL,
                    "dscp": dscp  # this is the dscp which will be matched
                }
                traffic_rule = {
                    "match": match,
                    # tos will be changed to this (new dscp inside)
                    "dscp": tos
                }
                slices.append(dscp_slice)
                # self.set_slices(dscp_slice)
                # check if the match and action are already in the list
                if not self.check_traffic_rule_exists(traffic_rule):
                    traffic_rules.append(traffic_rule)

        if len(slices) > 0:
            self.make_slices(slices)

        if len(traffic_rules) > 0:
            self.send_traffic_rules(traffic_rules)
        print()

    def make_slices(self, slices):
        """Creates New Slices and modifies the existing slices' quantum value"""
        total_quantum = 10000 # Assume total quantum is 10000 
        total_slice_share = 0
        wifi_slices = self.context.wifi_slices.keys() # Get all the existing slices
        wifi_slices = [int(i) for i in wifi_slices]
        slices.extend(wifi_slices) # add that to the list of slices that need to be created
        slices = set(slices) # make it a set so that no slice is repeated

        for dscp in slices:
            unit = self.get_dscp_unit(dscp)
            total_slice_share += unit
        
        unit_quantum = total_quantum/total_slice_share
        for dscp_slice in slices:
            unit = self.get_dscp_unit(dscp_slice)
            quantum = unit * unit_quantum

            # If slice already exists
            if str(dscp_slice) in self.context.wifi_slices:
                slice = self.context.wifi_slices[str(dscp_slice)]
                # If slice quantum is different than the what was just calculated
                if quantum != slice.properties['quantum']:
                    self.set_slices(dscp_slice, quantum)
            # New Slice 
            else:
                self.set_slices(dscp_slice, quantum)  # the slice for the dscp

    def get_dscp_unit(self, dscp):
        """Essentially the level of priority a slice should have over others. Decides the quantum value"""
        group_dscp = self.get_dscp_group(dscp)
        unit_map = {
            8: 0.5,
            0: 1,
            24: 1.5,
            32: 2,
            46: 3,
            48: 4
        }

        return unit_map[group_dscp]

    def loop(self):
        """Send out requests"""
        self.wtps_count = 0
        for wtp in self.wtps.values():

            if not wtp.connection:
                continue
            self.wtps_count += 1
            msg = Container(length=WIFI_DSCP_STATS_REQUEST.sizeof(),
                            ssid=self.context.wifi_props.ssid.to_raw())

            wtp.connection.send_message(PT_WIFI_DSCP_STATS_REQUEST,
                                        msg,
                                        self.handle_response)

    def handle_response(self, response, *_):
        """Handle WIFI_SLICE_STATS_RESPONSE message."""

        wtp = EtherAddress(response.device)

        # update this object
        if wtp not in self.stats:
            self.stats[wtp] = {}

        # generate data points
        points = []
        timestamp = datetime.utcnow()

        # make own stats, logic for traffic rules and slice creation.

        print("entries received: ", response.nb_entries)

        packets = []

        # Packet statistics
        for entry in response.stats:

            # print("entry", entry)
            packet = {
                "dscp": entry.dscp,
                "protocol": entry.protocol,
                "src_ip": entry.src_ip,
                "dst_ip": entry.dst_ip,
                "src_port": entry.src_port,
                "dst_port": entry.dst_port
            }

            packets.append(packet)

        # DSCP Statistics
        dscpMap = {}
        dscpPoints = []
        for dscp_pair in response.dscp_map:
            dscpMap[dscp_pair.code] = [
                dscp_pair.count, dscp_pair.avg_packet_size]

            # For every dscp, note down the amount and average packet size
            tags = dict(self.params)

            sample = {
                "measurement": self.name,
                "tags": tags,
                "timestamp": timestamp,
                "fields": {
                    f"{dscp_pair.code}_count": dscp_pair.count,
                    f"{dscp_pair.code}_avg_packet_size": dscp_pair.avg_packet_size,
                }
            }
            dscpPoints.append(sample)
        
        #  These values might also be useful for database points
        # "total_packets": response.nb_entries,
        # "total_dscp_counts": response.dscp_map_count,

       # save to db
        self.write_points(dscpPoints)

        packetStats = {
            "dscp_map_count": response.dscp_map_count,
            "dscp_stats_count": response.nb_entries,
            "packets": packets,
            "dscp_map": dscpMap,
        }

        self.stats[wtp] = packetStats
        self.make_traffic_rules()

        # handle callbacks
        self.handle_callbacks()

    def get_hash_match(self, match):
        key = match["src_port"] + match["dst_port"] + \
            match["protocol"] + match["dscp"]
        src_ip = hash(match["src_ip"][0]) + hash(match["src_ip"][1]) + \
            hash(match["src_ip"][2]) + hash(match["src_ip"][3])
        dst_ip = hash(match["dst_ip"][0]) + hash(match["dst_ip"][1]) + \
            hash(match["dst_ip"][2]) + hash(match["dst_ip"][3])
        key += src_ip + dst_ip
        return key

    def get_dscp_group(self, dscp):
        group_map = {
            0: 0,  # Best Effor

            8: 8,  # CS1 (Scavenger) -> CS1 (Background)
            16: 0,  # CS2 (Class Priority - Net. Mgnt.) -> Best Effort
            24: 24,  # CS3 (Class Priority) -> Braodcast Video
            32: 32,  # CS4 (Class Priority) -> CS4 (Streaming)
            40: 24,  # CS5 (High Priotrity/Signaling) -> CS3 (Streaming)
            48: 48,  # CS6 (Routing) -> CS6
            56: 48,  # CS7 (Class Priority - Net. Mgnt.) -> CS6

            10: 0,  # AF11 (High throughput data) -> Best Effort
            12: 0,  # AF12 (High throughput data) -> Best Effort
            14: 0,  # AF13 (High throughput data) -> Best Effort
            18: 0,  # AF21 (Low Latency Data) -> Best Effort
            20: 0,  # AF22 (Low Latency Data) -> Best Effort
            22: 0,  # AF23 (Low Latency Data) -> Best Effort
            26: 24,  # AF31 (Multimedia Streaming) -> CS3 (Braodcast Video)
            28: 24,  # AF32 (Multimedia Streaming) -> CS3 (Braodcast Video)
            30: 24,  # AF33 (Multimedia Streaming) -> CS3 (Braodcast Video)
            # AF41 (Mutlimedia Conferencing) -> CS4 (Real Time Interactive)
            34: 32,
            # AF42 (Mutlimedia Conferencing) -> CS4 (Real Time Interactive)
            36: 32,
            # AF43 (Mutlimedia Conferencing) -> CS4 (Real Time Interactive)
            38: 32,

            46: 46,  # EF -> EF

            44: 46,  # Voice Admit -> EF
        }
        if dscp not in group_map:
            return 0
        return group_map[dscp]

    def get_tos(self, dscp):
        tos_to_dscp_map = {
            0: 0,

            8: 32,
            16: 64,
            24: 96,
            32: 128,
            40: 160,
            48: 192,
            56: 224,

            10: 40,
            12: 48,
            14: 56,
            18: 72,
            20: 80,
            22: 88,
            26: 104,
            28: 112,
            30: 120,
            34: 136,
            36: 144,
            38: 152,

            46: 184,

            44: 176
        }

        if dscp not in tos_to_dscp_map:
            return 0
        return tos_to_dscp_map[dscp]


def launch(context, service_id, every=EVERY):
    """ Initialize the module. """

    return DSCPStats(context=context, service_id=service_id,  every=every)
