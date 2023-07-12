#!/bin/env python3
# Original Script by JayJay, provided by Fuuujin
# Scripted Edited and Improved by Toys0125
from pythonosc import udp_client
from pythonosc import dispatcher
from pythonosc import osc_server
import threading
import sys
import csv
import time
import os
import logging
import json


config = {}
if (not os.path.exists('config.json')):
    config['serverPort'] = 9001
    config['serverIp'] = '127.0.0.1'
    config['clientPort'] = 9000
    config['clientIp'] = '127.0.0.1'
    config['packetDelay'] = 0.2
    config['debugMode'] = False
    config['switchPacketOrder'] = False
    with open('config.json', 'a+') as outfile:
        json.dump(config, outfile, indent=2)
else:
    config = json.load(open('config.json', 'r'))
if (config['debugMode']):
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

OSC_FloatId = 0
OSC_FloatValue = 0.0
sleep_delay = config['packetDelay']
numFloats = 0
serverThread = None
avatarid = "Empty"
rows = [0.0]
globalLock = threading.Lock()
changingValue = False


def start_server(ip=config['serverIp'], port=config['serverPort']):
    global serverThread
    # This defines the server for receiving OSC messages
    logging.info(f"Listening on {ip}:{port}")
    server = osc_server.ThreadingOSCUDPServer((ip, port), dispatcher)
    serverThread = threading.Thread(target=server.serve_forever)
    serverThread.daemon = True
    serverThread.start()


client = udp_client.SimpleUDPClient(config['clientIp'], config['clientPort'])


def send_message(address, value):
    # This defines sending OSC messages
    logging.debug(f"Send {address} : {value}")
    thread = threading.Thread(
        target=client.send_message, args=(address, value))
    thread.start()


def handle_float_id(address, *args):
    # Added numFloats
    global OSC_FloatId, OSC_FloatValue, numFloats, globalLock, rows, changingValue

    logging.debug(f"Start handle_float_id")

    # float id resets to 0 when a radial puppet menu was just closed.
    if args[1] == 0:
        # Now we can save the last value to our csv.
        logging.info(f"changing id: {OSC_FloatId}")
        rows[OSC_FloatId-1] = [round(OSC_FloatValue, 2)]
        write_float(OSC_FloatId, OSC_FloatValue)
        changingValue = False
        return

    # float id is non-zero, thus a radial puppet is currently open. Save float id for later and wait.
    OSC_FloatId = args[1]
    numFloats = max(numFloats, OSC_FloatId)  # added
    logging.info(f"remembering float id: {args[1]}")
    with globalLock:
        if len(rows) < OSC_FloatId:
            logging.info(f"More parameters than expected")
            logging.debug('Difference is %s', (OSC_FloatId - len(rows)))
            # Add empty rows if necessary
            rows.extend([[0.0]] * (OSC_FloatId - len(rows)))
            logging.debug(f"{len(rows)} rows and data of %s", rows)


sendingValues = False


def handle_float_value(address, *args):
    global OSC_FloatValue, OSC_FloatId, changingValue, sendingValues
    OSC_FloatValue = args[1]
    logging.debug(f"remembering float value: {args[1]}")
    # thread = threading.Thread(target=changeDataRows) # Insurance that there will be atleast a thread after each change.
    # thread.start()
    if (not sendingValues):  # Hopefully reducing lag when changing values.
        sendingValues = True
        # So issue would cause a lag in setting the settings if it you hold the value for a bit. Hopefully prevents lag.
        changeDataRows()


def changeDataRows():
    global OSC_FloatValue, OSC_FloatId, sendingValues, changingValue
    changingValue = True
    send_message("/avatar/parameters/OPS_Id", OSC_FloatId)
    send_message("/avatar/parameters/OPS_Float", OSC_FloatValue)
    sendingValues = False


def handle_avatar_change(address, *args):
    global avatarid, globalLock, changingValue
    avatarid = args[1]
    changingValue = True
    logging.info(f"Avatar id is:{args[1]}")
    with globalLock:
        initialize_csv()


def write_float(floatId, floatValue):
    global avatarid, globalLock
    floatValue = round(floatValue, 2)
    logging.info(f"write_float given {floatId} {floatValue}")

    with globalLock:
        with open(f'{avatarid}.csv', 'r') as csvfile:
            reader = csv.reader(csvfile)
            rows = list(reader)

            if len(rows) >= floatId:
                rows[floatId-1] = [floatValue]
            else:
                logging.info(f"Writing more parameters")
                # Add empty rows if necessary
                rows.extend([[0]] * (floatId - len(rows) - 1))
                rows.append([floatValue])

    with open(f'{avatarid}.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)


def initialize_csv():
    global numFloats, avatarid, rows, changingValue
    # For local Avatar testing local:Name
    avatarid = avatarid.replace(':', '_')
    rows = [0.0]
    if (not os.path.exists(f'{avatarid}.csv')):
        with open(f'{avatarid}.csv', 'x', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(rows)
    with open(f'{avatarid}.csv', 'r') as csvfile:
        reader = csv.reader(csvfile)
        localrows = list(reader)
        if (len(localrows) != 0):
            numFloats = len(rows)
            rows = localrows
    changingValue = False
    """ with open(f'{avatarid}.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows) """


count = 0


def send_floats():
    global count, globalLock, rows, changingValue
    # This part of the module sends the stored values in memory.
    # 3 Example values are being send here.
    if (changingValue):
        # send_message("/avatar/parameters/OPS_Id", 0)
        time.sleep(0.5)
        return
    # Doing this to reduce logging as I have issues with it using to much ram in the windows terminal.
    if (count > 10):
        logging.info(f"{len(rows)} Rows, Local Floats are %s", rows)
        count = 0
    count += 1
    with globalLock:
        for i, row in enumerate(rows):
            if (changingValue):
                break
            value = float(row[0])
            if(config['switchPacketOrder']):
                send_message("/avatar/parameters/OPS_Float", value)
                send_message("/avatar/parameters/OPS_Id", i + 1)
            else:
                send_message("/avatar/parameters/OPS_Id", i + 1)
                send_message("/avatar/parameters/OPS_Float", value)
            time.sleep(sleep_delay)


def main():
    # Maps an address to the dispatcher and receives a callback function.
    dispatcher.map("/avatar/parameters/OPS_ReceiveId",
                   handle_float_id, "OSC_OUT_FloatId")
    dispatcher.map("/avatar/parameters/OPS_ReceiveFloat",
                   handle_float_value, "OSC_OUT_FloatValue")
    dispatcher.map("/avatar/change", handle_avatar_change, "OSC_AVATAR_ID")
# initialize_csv()
    start_server()


def main_send():
    global avatarid
    if (avatarid == "Empty"):
        logging.info("Waiting on avatar change")
        time.sleep(1)
        return
    send_floats()


if __name__ == "__main__":
    dispatcher = dispatcher.Dispatcher()
    main()
    logging.debug(sys.version)
    while serverThread.is_alive():
        main_send()

    # holds the program alive while the thread is running in the background.
    input("Press Enter to quit... \n")
    print("Quitting...")
