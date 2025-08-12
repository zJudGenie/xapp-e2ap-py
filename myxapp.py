import src.e2ap_xapp as e2ap_xapp
from os import getenv
from time import sleep
from ricxappframe.e2ap.asn1 import IndicationMsg

import sys
sys.path.append("oai-oran-protolib/builds/")
from ran_messages_pb2 import *

BER_TRESHOLD = float(getenv('BER_TRESHOLD', 0.3))
TARGET_MCS_BAD_CHANN = int(getenv('TARGET_MCS_BAD_CHANN', 2))
TARGET_MCS_GOOD_CHANN = int(getenv('TARGET_MCS_GOOD_CHANN', 8))
MIN_MCS = int(getenv('MIN_MCS', 0))
MAX_MCS = int(getenv('MAX_MCS', 15))


def xappLogic():

    # instance xapp
    connector = e2ap_xapp.e2apXapp()

    # get gnbs connected to RIC
    gnb_id_list = connector.get_gnb_id_list()
    print("{} gNB connected to RIC, listing:".format(len(gnb_id_list)))
    for gnb_id in gnb_id_list:
        print(gnb_id)
    print("---------")

    # subscription requests
    for gnb in gnb_id_list:
        e2sm_buffer = e2sm_report_request_buffer()
        connector.send_e2ap_sub_request(e2sm_buffer,gnb)
        #connector.send_e2ap_control_request(e2sm_buffer,gnb)
    
    # read loop
    sleep_time = 4
    while True:
        print("Sleeping {}s...".format(sleep_time))
        sleep(sleep_time)

        messgs = connector.get_queued_rx_message()
        if len(messgs) == 0:
            print("{} messages received while waiting".format(len(messgs)))
            print("____")
        else:
            print("{} messages received while waiting, printing:".format(len(messgs)))
            for msg in messgs:
                if msg["message type"] == connector.RIC_IND_RMR_ID:
                    print("RIC Indication received from gNB {}, decoding E2SM payload".format(msg["meid"]))
                    indm = IndicationMsg()
                    indm.decode(msg["payload"])
                    resp = RAN_indication_response()
                    resp.ParseFromString(indm.indication_message)
                    print(resp)

                    # Check if UE_LIST is present in resp
                    if resp.param_map[1]:
                        ue_list = resp.param_map[1].ue_list
                        # execute logic
                        adapt_mcs_to_ber(ue_list)

                        e2sm_buffer = e2sm_control_request_buffer(ue_list)
                        connector.send_e2ap_control_request(e2sm_buffer, gnb)

                    print("___")
                else:
                    print("Unrecognized E2AP message received from gNB {}".format(msg["meid"]))


# Loop over UEs and modify the MCS according to the documented logic
# If the BER is above the threshold decrement the MCS by 1, increment it otherwise
# If the MCS is not contained in the received data from the gNB set to default values
def adapt_mcs_to_ber(ue_list: ue_list_m):
    for ue in ue_list.ue_info:
        curr_ue_ber_downlink = ue.ue_ber_downlink
        if curr_ue_ber_downlink:
            print(f"Received data[{ue.rnti}]: BER = {curr_ue_ber_downlink}, MCS = {ue.ue_mcs_downlink}")
            if curr_ue_ber_downlink >= BER_TRESHOLD:
                ue.ue_mcs_downlink = ue.ue_mcs_downlink - 1 or TARGET_MCS_BAD_CHANN
            else:
                ue.ue_mcs_downlink = ue.ue_mcs_downlink + 1 or TARGET_MCS_GOOD_CHANN

            # make sure MCS stays within valid values
            ue.ue_mcs_downlink = clamp(ue.ue_mcs_downlink, MIN_MCS, MAX_MCS)


# build the buffer containing the indication request with GNB_ID and UE_LIST parameters
def e2sm_report_request_buffer():
    master_mess = RAN_message()
    master_mess.msg_type = RAN_message_type.INDICATION_REQUEST
    inner_mess = RAN_indication_request()
    inner_mess.target_params.extend([RAN_parameter.GNB_ID, RAN_parameter.UE_LIST])
    master_mess.ran_indication_request.CopyFrom(inner_mess)
    buf = master_mess.SerializeToString()
    return buf


# build the buffer containing the control request to be sent to the gNB
# take as input the ue_list to be encoded
def e2sm_control_request_buffer(ue_list: ue_list_m):
    master_mess = RAN_message()
    master_mess.msg_type = RAN_message_type.CONTROL

    inner_mess = RAN_control_request()

    map_entry = RAN_param_map_entry()
    map_entry.key = RAN_parameter.UE_LIST
    map_entry.ue_list.CopyFrom(ue_list)

    inner_mess.target_param_map.append(map_entry)

    master_mess.ran_control_request.CopyFrom(inner_mess)
    buf = master_mess.SerializeToString()
    return buf

def clamp(value, min_val, max_val):
    return max(min(value, max_val), min_val)

if __name__ == "__main__":
    xappLogic()